"""T1: can current TESS archive values distinguish resolved and unresolved TOIs?

Executes the preregistered smoke test in
``docs/coordination/TESS_RESOLUTION_SHIFT_PREREGISTRATION.md``.

This measures a property of the current catalog snapshot, not the accuracy of
a planet-vetting model. It never trains a planet classifier. The archive does
not provide historical values for these features at disposition time, so this
test cannot establish that they were available at triage. Distinguishability
also does not establish an accuracy gap; that requires outcome labels or a
clearly limited simulation.

The preregistration fixes the model, split, metric, direction, falsifier and
stopping rule. Do not add models or tune after seeing results; report an
inconclusive result as inconclusive.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
USER_AGENT = "FORGE-science-tess-shift/0.1"
TOI_TABLE = "toi"
TOI_DISPOSITION_COLUMN = "tfopwg_disp"

LABEL_EXCLUDED_COLUMNS = {TOI_DISPOSITION_COLUMN, "toi", "tid", "toipfx", "sectors"}
TIMESTAMP_COLUMNS = ("toi_created", "rowupdate", "release_date")
TIMESTAMP_DERIVED = {column: f"ts_{column}_days" for column in TIMESTAMP_COLUMNS}
TIMESTAMP_EPOCH = "2018-01-01"
FEATURE_PREFIXES = ("pl_", "st_")
DERIVED_SUFFIXES = ("symerr", "lim")

N_SPLITS = 5
SEEDS = (0, 1, 2, 3, 4)
N_BOOTSTRAP = 2000
N_PERMUTATIONS = 200
MODEL_KWARGS = {"max_iter": 2000, "random_state": 0}

RESOLVED_STATES = ("CP", "FP")
UNRESOLVED_STATES = ("PC", "APC")


class ArchiveError(RuntimeError):
    """Raised when the archive could not be queried after retries."""


def fetch_toi(columns: tuple[str, ...], timeout: int = 600, retries: int = 5) -> tuple[list[dict[str, str]], str]:
    query = f"select {','.join(columns)} from {TOI_TABLE}"
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            text = raw.decode("utf-8-sig", errors="replace")
            return list(csv.DictReader(io.StringIO(text))), hashlib.sha256(raw).hexdigest()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            time.sleep(15 * (attempt + 1))
    raise ArchiveError(f"could not fetch {TOI_TABLE}: {last}")


def load_toi_csv(path: str, expect_sha256: str | None = None) -> tuple[list[dict[str, str]], str]:
    """Rows and sha256 of a saved TOI CSV, so T1 can be re-run on a pinned snapshot."""
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expect_sha256 and digest != expect_sha256:
        raise ValueError(f"{path} has sha256 {digest}, expected {expect_sha256}")
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))), digest


def to_float(value: str | None) -> float:
    raw = (value or "").strip()
    if not raw:
        return np.nan
    try:
        return float(raw)
    except ValueError:
        return np.nan


def parse_timestamp_days(value: str | None) -> float:
    """Parse an archive timestamp into days since TIMESTAMP_EPOCH.

    The timestamp columns are strings. Passing them through ``to_float`` yields
    an all-NaN column, so a sensitivity arm that includes them must convert
    them to a numeric day offset or it measures nothing.
    """
    raw = (value or "").strip()
    if not raw:
        return np.nan
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return (parsed - datetime.strptime(TIMESTAMP_EPOCH, "%Y-%m-%d")).total_seconds() / 86400.0
    return np.nan


def add_timestamp_features(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched = []
    for row in rows:
        copy = dict(row)
        for column, derived in TIMESTAMP_DERIVED.items():
            copy[derived] = str(parse_timestamp_days(row.get(column)))
        enriched.append(copy)
    return enriched


def select_feature_columns(
    all_columns: list[str], include_timestamps: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Return numeric feature columns plus a reason for each excluded column."""
    excluded: dict[str, str] = {}
    features: list[str] = []
    for column in all_columns:
        if column in LABEL_EXCLUDED_COLUMNS:
            excluded[column] = "identifier or label"
            continue
        if column in TIMESTAMP_COLUMNS:
            if not include_timestamps:
                excluded[column] = "timestamp; encodes resolution age rather than triage features"
                continue
            excluded[column] = "converted to a numeric day offset for the sensitivity arm"
            continue
        if not column.startswith(FEATURE_PREFIXES):
            excluded[column] = "not a pl_ or st_ measurement"
            continue
        if column.endswith(DERIVED_SUFFIXES):
            excluded[column] = "asymmetric-error or detection-limit derivation"
            continue
        features.append(column)
    if include_timestamps:
        features.extend(TIMESTAMP_DERIVED.values())
    return sorted(set(features)), excluded


def build_arrays(
    rows: list[dict[str, str]],
    feature_columns: list[str],
    resolved_states: tuple[str, ...],
    unresolved_states: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, Counter, dict[str, int]]:
    labels: list[int] = []
    groups: list[str] = []
    rows_kept: list[dict[str, str]] = []
    dropped: Counter[str] = Counter()
    for row in rows:
        state = (row.get(TOI_DISPOSITION_COLUMN) or "").strip().upper()
        tid = (row.get("tid") or "").strip()
        if not tid:
            dropped["missing_tid"] += 1
            continue
        if state in resolved_states:
            labels.append(1)
        elif state in unresolved_states:
            labels.append(0)
        else:
            dropped[f"state_{state or '(blank)'}"] += 1
            continue
        rows_kept.append(row)
        groups.append(tid)

    matrix = np.empty((len(rows_kept), len(feature_columns)), dtype=float)
    for i, row in enumerate(rows_kept):
        for j, column in enumerate(feature_columns):
            matrix[i, j] = to_float(row.get(column))

    y = np.asarray(labels, dtype=int)
    return matrix, y, np.asarray(groups), dropped, dict(Counter(groups))


def drop_empty_columns(
    matrix: np.ndarray, feature_columns: list[str]
) -> tuple[np.ndarray, list[str], list[str]]:
    """Remove columns with no observed value so the imputer never sees one."""
    keep = [j for j in range(matrix.shape[1]) if not bool(np.all(np.isnan(matrix[:, j])))]
    dropped = [feature_columns[j] for j in range(matrix.shape[1]) if j not in set(keep)]
    return matrix[:, keep], [feature_columns[j] for j in keep], dropped


def make_model() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(**MODEL_KWARGS)),
        ]
    )


def grouped_oof_auc(
    matrix: np.ndarray, y: np.ndarray, groups: np.ndarray, seeds: tuple[int, ...]
) -> tuple[np.ndarray, dict]:
    """Out-of-fold ROC AUC per seed, plus the mean out-of-fold score vector."""
    per_seed: dict[str, float] = {}
    score_vectors = []
    for seed in seeds:
        splitter = GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed)
        oof = np.zeros(len(y), dtype=float)
        for train_idx, test_idx in splitter.split(matrix, y, groups):
            model = make_model()
            model.fit(matrix[train_idx], y[train_idx])
            oof[test_idx] = model.predict_proba(matrix[test_idx])[:, 1]
        per_seed[str(seed)] = float(roc_auc_score(y, oof))
        score_vectors.append(oof)
    mean_oof = np.mean(score_vectors, axis=0)
    return mean_oof, per_seed


def cluster_bootstrap_auc(
    y: np.ndarray, scores: np.ndarray, groups: np.ndarray, n_boot: int, seed: int
) -> dict:
    rng = np.random.default_rng(seed)
    unique = np.unique(groups)
    index_by_group = {g: np.flatnonzero(groups == g) for g in unique}
    values = []
    for _ in range(n_boot):
        picked = rng.choice(unique, size=len(unique), replace=True)
        idx = np.concatenate([index_by_group[g] for g in picked])
        if len(np.unique(y[idx])) < 2:
            continue
        values.append(float(roc_auc_score(y[idx], scores[idx])))
    if not values:
        return {"n_effective": 0}
    array = np.asarray(values)
    return {
        "n_effective": len(array),
        "mean": float(array.mean()),
        "ci95_low": float(np.percentile(array, 2.5)),
        "ci95_high": float(np.percentile(array, 97.5)),
    }


def permutation_null(
    matrix: np.ndarray, y: np.ndarray, groups: np.ndarray, n_permutations: int, seed: int
) -> dict:
    rng = np.random.default_rng(seed)
    splitter = GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=0)
    splits = list(splitter.split(matrix, y, groups))
    values = []
    for _ in range(n_permutations):
        permuted = y[rng.permutation(len(y))]
        oof = np.zeros(len(y), dtype=float)
        for train_idx, test_idx in splits:
            model = make_model()
            model.fit(matrix[train_idx], permuted[train_idx])
            oof[test_idx] = model.predict_proba(matrix[test_idx])[:, 1]
        if len(np.unique(permuted)) < 2:
            continue
        values.append(float(roc_auc_score(permuted, oof)))
    array = np.asarray(values)
    return {
        "n_permutations": len(array),
        "mean": float(array.mean()) if len(array) else None,
        "max": float(array.max()) if len(array) else None,
        "p95": float(np.percentile(array, 95)) if len(array) else None,
    }


def missingness(matrix: np.ndarray, feature_columns: list[str]) -> dict:
    all_missing = [c for c, j in zip(feature_columns, range(matrix.shape[1])) if bool(np.all(np.isnan(matrix[:, j])))]
    mostly_missing = [
        {"column": c, "fraction_missing": round(float(np.mean(np.isnan(matrix[:, j]))), 4)}
        for c, j in zip(feature_columns, range(matrix.shape[1]))
        if np.mean(np.isnan(matrix[:, j])) > 0.5
    ]
    return {
        "all_nan_columns_dropped_by_imputer": all_missing,
        "columns_over_half_missing": mostly_missing,
        "overall_cell_missing_fraction": round(float(np.mean(np.isnan(matrix))), 4),
    }


def run_arm(
    rows: list[dict[str, str]],
    all_columns: list[str],
    arm_name: str,
    include_timestamps: bool,
    resolved_states: tuple[str, ...],
    unresolved_states: tuple[str, ...],
    n_bootstrap: int,
    n_permutations: int,
    seed: int,
) -> dict:
    features, excluded = select_feature_columns(all_columns, include_timestamps=include_timestamps)
    source_rows = add_timestamp_features(rows) if include_timestamps else rows
    matrix, y, groups, dropped, host_counts = build_arrays(
        source_rows, features, resolved_states, unresolved_states
    )
    if len(np.unique(y)) < 2:
        raise ValueError(f"arm {arm_name} has a single class")

    requested_features = len(features)
    matrix, features, empty_columns = drop_empty_columns(matrix, features)

    started = time.perf_counter()
    mean_oof, per_seed = grouped_oof_auc(matrix, y, groups, SEEDS)
    auc = float(roc_auc_score(y, mean_oof))
    bootstrap = cluster_bootstrap_auc(y, mean_oof, groups, n_bootstrap, seed)
    elapsed = time.perf_counter() - started

    excludes_zero = bootstrap.get("n_effective", 0) > 0 and bootstrap["ci95_low"] > 0.5
    includes_zero = bootstrap.get("n_effective", 0) > 0 and bootstrap["ci95_high"] < 0.5

    return {
        "arm": arm_name,
        "resolved_states": list(resolved_states),
        "unresolved_states": list(unresolved_states),
        "includes_timestamp_columns": include_timestamps,
        "n_rows": int(len(y)),
        "n_features": len(features),
        "n_features_requested": requested_features,
        "columns_dropped_all_missing": empty_columns,
        "n_hosts": len(host_counts),
        "hosts_with_multiple_tois": int(sum(1 for v in host_counts.values() if v > 1)),
        "class_counts": {"resolved": int(np.sum(y == 1)), "unresolved": int(np.sum(y == 0))},
        "dropped_rows_by_reason": dropped,
        "feature_columns": features,
        "excluded_columns": excluded,
        "missingness": missingness(matrix, features),
        "oof_auc": auc,
        "oof_auc_per_seed": per_seed,
        "cluster_bootstrap_auc": bootstrap,
        "ci_excludes_half": bool(excludes_zero or includes_zero),
        "ci_below_half": bool(includes_zero),
        "prediction_supported": bool(excludes_zero),
        "falsifier_triggered": bool(includes_zero),
        "inconclusive": not bool(excludes_zero or includes_zero),
        "elapsed_seconds": round(elapsed, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="schemas/examples/tess-resolution-shift.json")
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--permutations", type=int, default=N_PERMUTATIONS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--skip-permutation", action="store_true")
    parser.add_argument("--csv", help="read a saved TOI CSV (e.g. the pinned snapshot) instead of querying the archive")
    parser.add_argument("--expect-sha256", help="with --csv: refuse the file unless its sha256 matches")
    args = parser.parse_args()

    if args.csv:
        rows, digest = load_toi_csv(args.csv, args.expect_sha256)
        all_columns = sorted(rows[0].keys()) if rows else []
        print(f"loaded {args.csv}: {len(rows)} rows, {len(all_columns)} columns, sha256={digest}")
    else:
        all_columns = sorted(
            {
                "toi",
                "tid",
                TOI_DISPOSITION_COLUMN,
                *TIMESTAMP_COLUMNS,
                *_discover_columns(args.timeout),
            }
        )
        rows, digest = fetch_toi(tuple(all_columns), timeout=args.timeout)
        print(f"fetched {TOI_TABLE}: {len(rows)} rows, {len(all_columns)} columns")

    arms = [
        ("primary_cp_fp_vs_pc_apc", False, RESOLVED_STATES, UNRESOLVED_STATES),
        ("with_timestamps", True, RESOLVED_STATES, UNRESOLVED_STATES),
        ("fa_counted_as_resolved", False, (*RESOLVED_STATES, "FA"), UNRESOLVED_STATES),
    ]
    results = []
    for name, timestamps, resolved, unresolved in arms:
        arm = run_arm(
            rows,
            all_columns,
            name,
            timestamps,
            resolved,
            unresolved,
            args.bootstrap,
            args.permutations,
            args.seed,
        )
        results.append(arm)
        print(
            f"\n[{name}] rows={arm['n_rows']} features={arm['n_features']} hosts={arm['n_hosts']}\n"
            f"  oof_auc={arm['oof_auc']:.4f} "
            f"ci95=[{arm['cluster_bootstrap_auc'].get('ci95_low', float('nan')):.4f}, "
            f"{arm['cluster_bootstrap_auc'].get('ci95_high', float('nan')):.4f}] "
            f"prediction_supported={arm['prediction_supported']} "
            f"falsifier={arm['falsifier_triggered']} ({arm['elapsed_seconds']}s)"
        )

    primary = results[0]
    permutation = None
    if not args.skip_permutation:
        features, _ = select_feature_columns(all_columns, include_timestamps=False)
        matrix, y, groups, _, _ = build_arrays(rows, features, RESOLVED_STATES, UNRESOLVED_STATES)
        matrix, _, _ = drop_empty_columns(matrix, features)
        permutation = permutation_null(matrix, y, groups, args.permutations, args.seed)
        print(
            f"\npermutation null: mean={permutation['mean']:.4f} "
            f"max={permutation['max']:.4f} p95={permutation['p95']:.4f}"
        )

    report = {
        "status": "SHIFT_MEASUREMENT_ONLY_NOT_VETTING_ACCURACY_NOT_BENCHMARK_EVIDENCE",
        "preregistration": "docs/coordination/TESS_RESOLUTION_SHIFT_PREREGISTRATION.md",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": f"NASA Exoplanet Archive TAP table {TOI_TABLE}" + (f" (saved copy {args.csv})" if args.csv else ""),
        "sha256_raw_csv": digest,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "sklearn": __import__("sklearn").__version__,
            "platform": platform.platform(),
        },
        "protocol": {
            "model": "LogisticRegression(max_iter=2000) on median-imputed standardized features",
            "split": f"GroupKFold(n_splits={N_SPLITS}, shuffle=True) grouped on tid",
            "seeds": list(SEEDS),
            "primary_metric": "out-of-fold ROC AUC, resolved vs unresolved, direction above 0.5",
            "bootstrap": {"iterations": args.bootstrap, "unit": "tid cluster", "interval": "95% percentile"},
            "permutation_control": {"iterations": args.permutations},
            "stopping_rule": "primary arm plus sensitivity arms only; no model added after results",
        },
        "arms": results,
        "permutation_null_primary_arm": permutation,
        "verdict": {
            "primary_arm_auc": primary["oof_auc"],
            "primary_arm_ci95": [
                primary["cluster_bootstrap_auc"].get("ci95_low"),
                primary["cluster_bootstrap_auc"].get("ci95_high"),
            ],
            "shift_detected": primary["prediction_supported"],
            "falsifier_triggered": primary["falsifier_triggered"],
            "inconclusive": primary["inconclusive"],
            "conclusion": (
                "In the current catalog snapshot, these fields distinguish resolved from unresolved "
                "TOIs. Historical availability at triage was not established, and this result does "
                "not measure a vetting-accuracy gap. Further feature-provenance and prior-art review "
                "is required before designing T2."
                if primary["prediction_supported"]
                else "The prediction of separation was not supported. If the interval overlaps 0.5, "
                "the result is inconclusive; it does not establish exchangeability or rule out an "
                "accuracy gap."
            ),
        },
        "interpretation_limits": [
            "This measures feature-distribution difference between resolved and unresolved TOIs.",
            "It does not measure planet-vetting accuracy and never trains a planet classifier.",
            "A detectable shift is neither necessary nor sufficient for an accuracy gap; no "
            "vetting-accuracy gap was measured.",
            "Association is not causation. Shift may reflect how TFOPWG triages rather than how "
            "astronomers triage.",
            "The falsifier requires the whole interval below 0.5, so under a true null it still "
            "fires about 2.5% of the time by chance. The permutation control, not the point "
            "estimate, is what rules out a broken pipeline.",
            "Not benchmark evidence, not a novelty claim, and not a locked science contract.",
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {output}")


def _discover_columns(timeout: int) -> list[str]:
    query = "select column_name from TAP_SCHEMA.columns where table_name='toi' order by column_name"
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return [row["column_name"] for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))]


if __name__ == "__main__":
    main()
