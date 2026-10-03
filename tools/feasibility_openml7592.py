"""One-off FORGE feasibility run on OpenML task 7592 (adult).

Runs the first published stratified CV fold with two matched sklearn pipelines.
This is a smoke/feasibility check, not benchmark evidence or a protocol.
Dependencies: numpy, scikit-learn. Downloaded task/data/splits are pinned by
OpenML IDs and saved to the user cache; outputs are printed as JSON.
"""
from __future__ import annotations

import csv
import hashlib
import json
import argparse
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits


BASE = "https://www.openml.org"
TASK_ID = 7592
DATA_ID = 1590
DATA_URL = f"{BASE}/data/v1/download/1595261/adult.arff"
TASK_URL = f"{BASE}/api/v1/json/task/{TASK_ID}"
CACHE = Path.home() / ".cache" / "forge-openml-feasibility"
CACHE.mkdir(parents=True, exist_ok=True)


def fetch(url: str, filename: str) -> bytes:
    path = CACHE / filename
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "FORGE-feasibility/0.1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def parse_arff(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = raw.decode("utf-8", errors="replace")
    attrs: list[str] = []
    rows: list[dict[str, str]] = []
    in_data = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("%"):
            continue
        if line.lower().startswith("@attribute"):
            # OpenML ARFF attribute names in this dataset contain no spaces.
            attrs.append(line.split()[1].strip("'\""))
        elif line.lower() == "@data":
            in_data = True
        elif in_data:
            values = next(csv.reader([line], skipinitialspace=True))
            rows.append(dict(zip(attrs, [v.strip().strip("'\"") for v in values])))
    if not rows:
        raise RuntimeError("ARFF parser found no rows")
    return attrs, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="schemas/examples/openml-7592-feasibility.json")
    args = parser.parse_args()
    task = json.loads(fetch(TASK_URL, "task-7592.json"))[
        "task"
    ]
    data_meta = json.loads(fetch(f"{BASE}/api/v1/json/data/{DATA_ID}", "data-1590.json"))[
        "data_set_description"
    ]
    split_url = next(
        x["estimation_procedure"]["data_splits_url"]
        for x in task["input"]
        if x["name"] == "estimation_procedure"
    )
    splits, rows = parse_arff(fetch(DATA_URL, "adult.arff"))
    _, split_rows = parse_arff(
        (b"@relation splits\n@attribute type {TRAIN,TEST}\n@attribute rowid numeric\n"
         b"@attribute repeat numeric\n@attribute fold numeric\n@data\n")
        + b"\n".join(
            (",".join(line.strip().split(","))).encode()
            for line in fetch(split_url, "task-7592-splits.arff").decode().splitlines()
            if line.strip() and not line.strip().startswith("@")
        )
    )
    # Native first-fold split indices are zero-based row IDs from OpenML.
    first_fold = [r for r in split_rows if r["repeat"] == "0" and r["fold"] == "0"]
    train_ids = [int(r["rowid"]) for r in first_fold if r["type"] == "TRAIN"]
    test_ids = [int(r["rowid"]) for r in first_fold if r["type"] == "TEST"]
    if not train_ids or not test_ids:
        raise RuntimeError("OpenML task split did not contain repeat 0 / fold 0")

    target = task["input"][0]["data_set"]["target_feature"]
    feature_names = [name for name in splits if name.lower() != target.lower()]
    categorical = ["workclass", "education", "marital-status", "occupation",
                   "relationship", "race", "sex", "native-country"]
    categorical = [c for c in categorical if c in feature_names]
    numeric = [c for c in feature_names if c not in categorical]
    X = pd.DataFrame([{k: (np.nan if row[k] == "?" else row[k]) for k in feature_names} for row in rows])
    y = np.asarray([1 if row[target].strip() == ">50K" else 0 for row in rows], dtype=np.int8)
    missing_cells = sum(v == "?" for row in rows for v in row.values())
    missing_features = sum(any(row[c] == "?" for row in rows) for c in feature_names)
    missing_rows = sum(any(row[c] == "?" for c in feature_names) for row in rows)

    def make_pipeline(indicators: bool) -> Pipeline:
        numeric_steps = [("impute", SimpleImputer(strategy="median", add_indicator=indicators)),
                         ("scale", StandardScaler())]
        categorical_steps = [("impute", SimpleImputer(strategy="most_frequent")),
                             ("encode", OneHotEncoder(handle_unknown="ignore"))]
        transformers = [
            ("numeric", Pipeline(numeric_steps), numeric),
            ("categorical", Pipeline(categorical_steps), categorical),
        ]
        if indicators:
            # Only the three Adult categorical columns with missing values.
            missing_cols = [c for c in ("workclass", "occupation", "native-country") if c in categorical]
            transformers.append(("categorical_missing", MissingIndicator(features="all"), missing_cols))
        transform = ColumnTransformer(transformers)
        return Pipeline([("preprocess", transform),
                         ("model", LogisticRegression(max_iter=1000, random_state=0))])

    results = []
    for label, indicators in [("median_mode", False), ("median_mode_plus_missing_indicators", True)]:
        started = time.perf_counter()
        model = make_pipeline(indicators)
        with threadpool_limits(limits=1):
            model.fit(X.iloc[train_ids], y[train_ids])
            probability = model.predict_proba(X.iloc[test_ids])[:, list(model.classes_).index(1)]
        prediction = (probability >= 0.5).astype(np.int8)
        runtime = time.perf_counter() - started
        results.append({
            "comparison": label,
            "roc_auc": float(roc_auc_score(y[test_ids], probability)),
            "log_loss": float(log_loss(y[test_ids], probability, labels=[0, 1])),
            "accuracy": float(accuracy_score(y[test_ids], prediction)),
            "runtime_seconds": round(runtime, 4),
        })

    result = {
        "status": "FEASIBILITY_ONLY_NOT_BENCHMARK_EVIDENCE",
        "task_id": TASK_ID,
        "task_name": task["task_name"],
        "dataset_id": DATA_ID,
        "dataset_name": data_meta["name"],
        "dataset_version": data_meta.get("version"),
        "dataset_license": data_meta.get("licence"),
        "split_protocol": "OpenML task native stratified 10-fold CV, repeat 0, fold 0 only",
        "split_sizes": {"train": len(train_ids), "test": len(test_ids)},
        "metric": {"primary_candidate": "roc_auc", "direction": "maximize", "source": "selected provisionally after review; OpenML task API lists no evaluation_measure", "secondary": ["log_loss", "accuracy"]},
        "model": "LogisticRegression(max_iter=1000, random_state=0)",
        "missing_cells_in_dataset": missing_cells,
        "rows_with_missing_feature_values": missing_rows,
        "features_with_missing_values": {c: sum(row[c] == "?" for row in rows) for c in feature_names if any(row[c] == "?" for row in rows)},
        "data_sha256": hashlib.sha256((CACHE / "adult.arff").read_bytes()).hexdigest(),
        "features_with_missing_feature_count": missing_features,
        "results": results,
        "setup_issues": ["OpenML Python client was not installed; fetched task metadata, data, and official split directly from OpenML APIs."],
        "caveats": ["Single fold and single seed; not inferential evidence.", "Provisional metric selection; subgroup fairness metrics and the full candidate comparison are not included in this one-fold feasibility check."],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

