"""Reproducible OpenML Adult task runner used by feasibility and bench arms.

Runner contract: run(task_id, params, seed) -> {"metrics": {name: value}}.
Each call evaluates one candidate over all folds in the task's official split.
The function downloads task data/splits once into the local cache and never
publishes runs to OpenML. It is deliberately scoped to Adult task 7592.
"""
from __future__ import annotations

import csv
import json
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

BASE = "https://www.openml.org"
TASK_ID = 7592
DATA_ID = 1590
MISSING_CATEGORICAL = ("workclass", "occupation", "native-country")
NUMERIC_FEATURES = ("age", "fnlwgt", "education-num", "capital-gain", "capital-loss", "hours-per-week")
TARGET_POSITIVE = ">50K"
CACHE = Path.home() / ".cache" / "forge-openml-feasibility"
CACHE.mkdir(parents=True, exist_ok=True)


def _fetch(url: str, filename: str) -> bytes:
    path = CACHE / filename
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "FORGE-openml-runner/0.1"})
        with urllib.request.urlopen(req, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def _parse_arff(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    attrs: list[str] = []
    rows: list[dict[str, str]] = []
    in_data = False
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("%"):
            continue
        if line.lower().startswith("@attribute"):
            attrs.append(line.split()[1].strip("'\""))
        elif line.lower() == "@data":
            in_data = True
        elif in_data:
            vals = next(csv.reader([line], skipinitialspace=True))
            rows.append(dict(zip(attrs, [v.strip().strip("'\"") for v in vals])))
    if not rows:
        raise ValueError("OpenML ARFF contained no records")
    return attrs, rows


@lru_cache(maxsize=1)
def _load_task() -> tuple[pd.DataFrame, np.ndarray, list[tuple[np.ndarray, np.ndarray]], dict[str, Any]]:
    task = json.loads(_fetch(f"{BASE}/api/v1/json/task/{TASK_ID}", "task-7592.json"))["task"]
    meta = json.loads(_fetch(f"{BASE}/api/v1/json/data/{DATA_ID}", "data-1590.json"))["data_set_description"]
    split_url = next(x["estimation_procedure"]["data_splits_url"] for x in task["input"]
                     if x["name"] == "estimation_procedure")
    names, rows = _parse_arff(_fetch(f"{BASE}/data/v1/download/1595261/adult.arff", "adult.arff"))
    target = task["input"][0]["data_set"]["target_feature"]
    features = [n for n in names if n != target]
    frame = pd.DataFrame([{k: (np.nan if r[k] == "?" else r[k]) for k in features} for r in rows])
    categorical = [c for c in features if c not in NUMERIC_FEATURES]
    for c in NUMERIC_FEATURES:
        if c in frame:
            frame[c] = pd.to_numeric(frame[c], errors="coerce")
    y = np.asarray([r[target].strip() == TARGET_POSITIVE for r in rows], dtype=np.int8)
    _, split_rows = _parse_arff(_fetch(split_url, "task-7592-splits.arff"))
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    reps = sorted({int(r["repeat"]) for r in split_rows})
    fold_ids = sorted({int(r["fold"]) for r in split_rows})
    for rep in reps:
        for fold in fold_ids:
            subset = [r for r in split_rows if int(r["repeat"]) == rep and int(r["fold"]) == fold]
            tr = np.asarray([int(r["rowid"]) for r in subset if r["type"] == "TRAIN"], dtype=int)
            te = np.asarray([int(r["rowid"]) for r in subset if r["type"] == "TEST"], dtype=int)
            if len(tr) and len(te):
                folds.append((tr, te))
    if len(folds) != 10:
        raise ValueError(f"Expected 10 official folds for task {TASK_ID}; found {len(folds)}")
    return frame, y, folds, meta


def _pipeline(model_name: str, strategy: str, seed: int, X: pd.DataFrame) -> Any:
    if model_name == "hgb_native":
        # HistGradientBoosting consumes pandas categorical dtypes directly and
        # handles categorical NaNs internally; no imputation is applied.
        return HistGradientBoostingClassifier(
            categorical_features="from_dtype", max_iter=100, random_state=seed
        )

    missing_cols = [c for c in MISSING_CATEGORICAL if c in X.columns]
    drop_cols = missing_cols if strategy == "drop" else []
    categorical = [c for c in X.columns if c not in NUMERIC_FEATURES and c not in drop_cols]
    numeric = [c for c in X.columns if c in NUMERIC_FEATURES and c not in drop_cols]
    if strategy not in {"mode", "mode_indicator", "own_category", "drop"}:
        raise ValueError(f"Unknown missing strategy: {strategy}")
    cat_imputer = (SimpleImputer(strategy="constant", fill_value="__MISSING__")
                   if strategy == "own_category" else SimpleImputer(strategy="most_frequent"))
    cat_pipe = Pipeline([("impute", cat_imputer),
                         ("encode", OneHotEncoder(handle_unknown="ignore",
                                                   sparse_output=model_name == "logistic"))])
    transformers: list[tuple[str, Any, list[str]]] = [
        ("categorical", cat_pipe, categorical),
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")),
                              ("scale", StandardScaler())]), numeric),
    ]
    if strategy == "mode_indicator":
        # Explicit indicators for the actual missing columns (categorical).
        transformers.append(("missing_flags", MissingIndicator(features="all"), missing_cols))
    prep = ColumnTransformer(transformers, remainder="drop")
    estimator = (LogisticRegression(max_iter=1000, random_state=0)
                 if model_name == "logistic" else
                 HistGradientBoostingClassifier(max_iter=100, random_state=seed)
                 if model_name == "hgb" else None)
    if estimator is None:
        raise ValueError(f"Unknown model: {model_name}")
    return Pipeline([("preprocess", prep), ("model", estimator)])


def _subgroup_auc_gap(y: np.ndarray, scores: np.ndarray, X: pd.DataFrame, column: str) -> float | None:
    aucs = []
    for value in pd.Series(X[column]).dropna().unique():
        mask = X[column].to_numpy() == value
        if len(np.unique(y[mask])) == 2:
            aucs.append(roc_auc_score(y[mask], scores[mask]))
    return float(max(aucs) - min(aucs)) if len(aucs) >= 2 else None


def run(task_id: int | str, params: dict, seed: int) -> dict:
    """Evaluate candidate across all 10 official folds and return aggregate metrics."""
    if str(task_id) != str(TASK_ID):
        raise ValueError(f"This runner supports OpenML task {TASK_ID}, got {task_id}")
    model_name = params.get("model", "logistic")
    strategy = params.get("strategy", "mode")
    X, y, folds, meta = _load_task()
    if model_name == "hgb_native":
        for c in X.columns:
            if X[c].dtype == object:
                X[c] = X[c].astype("category")
    scores = np.zeros(len(y), dtype=float)
    predicted = np.zeros(len(y), dtype=np.int8)
    losses: list[float] = []
    for train, test in folds:
        train_X, test_X = X.iloc[train].copy(), X.iloc[test].copy()
        if strategy == "drop":
            drop_cols = [c for c in MISSING_CATEGORICAL if c in train_X.columns]
            train_X, test_X = train_X.drop(columns=drop_cols), test_X.drop(columns=drop_cols)
        model = _pipeline(model_name, strategy, seed, train_X)
        with threadpool_limits(limits=1):
            model.fit(train_X, y[train])
            p = model.predict_proba(test_X)[:, 1]
        scores[test] = p
        predicted[test] = (p >= 0.5).astype(np.int8)
        losses.append(log_loss(y[test], p, labels=[0, 1]))
    sex_gap = _subgroup_auc_gap(y, scores, X, "sex")
    race_gap = _subgroup_auc_gap(y, scores, X, "race")
    available_gaps = [g for g in (sex_gap, race_gap) if g is not None]
    result = {
        "metrics": {
            "roc_auc": float(roc_auc_score(y, scores)),
            "log_loss": float(log_loss(y, scores, labels=[0, 1])),
            "accuracy": float(accuracy_score(y, predicted)),
            "sex_auc_gap": sex_gap,
            "race_auc_gap": race_gap,
            "subgroup_auc_gap": max(available_gaps) if available_gaps else None,
            "fold_log_loss_sd": float(np.std(losses, ddof=1)),
        },
        "task_id": TASK_ID,
        "dataset_id": DATA_ID,
        "dataset_version": meta.get("version"),
        "folds": len(folds),
        "seed": seed,
        "model": model_name,
        "strategy": strategy,
    }
    return result
