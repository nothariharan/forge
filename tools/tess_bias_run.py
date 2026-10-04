"""T2 runner: semi-synthetic resolution-bias simulation on TESS TOIs.

Implements the runner contract in bench/PROTOCOL_TESS.md section 6. Every
number this produces comes from a SIMULATION inside the labeled cohort
(CP vs FP+FA), where truth is known. It is not a measurement of vetting
accuracy on real unresolved TOIs.

One call:
1. Fits the resolution model (T1's model: resolved CP/FP/FA vs unresolved
   PC/APC) with tid-grouped 5-fold CV and takes each labeled TOI's
   out-of-fold score e(x). Deterministic and cached per data snapshot.
2. For each of `replicates` replicates, splits the labeled cohort's hosts
   into a pseudo-resolved set R* (share rho of TOIs) and a pseudo-unresolved
   set U*, sampling hosts without replacement with weight mean(e)^gamma.
3. Trains the vetting model with tid-grouped 5-fold CV inside R*. Per fold,
   the same fold model is scored on its held-out R* fold and on all of U*,
   so the naive estimate and the deployment truth share a training size.
4. Returns, averaged over replicates: the estimator's estimate of deployment
   AUC, the true deployment AUC, |error|, and the gap naive minus true.

Usage:
    run("tess-resolution-bias", {"model": "lr", "estimator": "naive", "gamma": 1}, seed=1)

Data: a cached copy of the TOI table. Set FORGE_TESS_CSV (default
results/cache/toi.csv) and FORGE_TESS_SHA256 (the pinned snapshot hash); the
runner refuses a file whose hash differs. Create the cache once with:

    python tools/tess_bias_run.py --fetch
"""
from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

if tuple(int(x) for x in re.findall(r"\d+", sklearn.__version__)[:2]) < (1, 6):
    raise ImportError(f"scikit-learn {sklearn.__version__} is too old: GroupKFold(shuffle=True) needs >= 1.6. "
                      "Install the pinned set: pip install -r requirements-science.txt")



def package_versions() -> dict[str, str | None]:
    """Versions that change the numbers; recorded with every pre-lock and lite-benchmark run."""
    from importlib import metadata
    out: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in ("numpy", "scikit-learn", "scipy", "pandas"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


sys.path.insert(0, str(Path(__file__).resolve().parent))

import tess_resolution_shift as t1  # noqa: E402  (same feature selection and model as T1)

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_ID = "tess-resolution-bias"
DEFAULT_CSV = REPO_ROOT / "results" / "cache" / "toi.csv"
# Pinned snapshot. Set when the cache is first created (see the protocol change log); "" means unpinned.
PINNED_SHA256 = ""

POSITIVE = ("CP",)
NEGATIVE = ("FP", "FA")
UNRESOLVED = ("PC", "APC")
RESOLVED = POSITIVE + NEGATIVE

RHO = 0.30
N_SPLITS = 5
DEFAULT_REPLICATES = 20
MIN_PER_CLASS = 10  # each class must appear at least this often in R* and in U*, or the replicate is invalid
MODELS = ("lr", "hgb")
ESTIMATORS = ("naive", "iw", "iw_clip")


# ---------------------------------------------------------------- data


def data_path() -> Path:
    return Path(os.environ.get("FORGE_TESS_CSV", DEFAULT_CSV))


SPEC_PATH = REPO_ROOT / "bench" / "specs" / "tess_resolution_bias.json"


def spec_path() -> Path:
    return Path(os.environ.get("FORGE_TESS_SPEC", SPEC_PATH))


def pinned_from_spec() -> str:
    """The pin lives in the task spec (data_ver "nasa-toi@<sha256>"), so there is one source of truth."""
    try:
        ver = json.loads(spec_path().read_text()).get("data_ver", "")
    except (OSError, ValueError):
        return ""
    sha = ver.split("@", 1)[-1]
    return sha if len(sha) == 64 and all(c in "0123456789abcdef" for c in sha) else ""


def expected_sha256() -> str:
    return os.environ.get("FORGE_TESS_SHA256") or PINNED_SHA256 or pinned_from_spec()


def load_rows(path: Path, expected: str) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; create it with `python tools/tess_bias_run.py --fetch`")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if not expected:
        raise ValueError(f"no pinned snapshot hash; set FORGE_TESS_SHA256 (this file is {digest})")
    if digest != expected:
        raise ValueError(f"{path} has sha256 {digest}, expected the pinned snapshot {expected}")
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))), digest


RESOLUTION_MODELS = ("lr", "hgb")  # lr = T1's model (primary); hgb = nonlinear sensitivity arm, reported only


def _resolution_model(kind: str):
    if kind == "lr":
        return t1.make_model()
    if kind == "hgb":
        return HistGradientBoostingClassifier(random_state=0)
    raise ValueError(f"resolution_model must be one of {RESOLUTION_MODELS}")


@functools.lru_cache(maxsize=8)
def prepare(path_str: str, expected: str, resolution_model: str = "lr") -> dict:
    """Load the snapshot, fit the resolution model once, and return the labeled cohort with e(x)."""
    rows, digest = load_rows(Path(path_str), expected)
    columns = list(rows[0].keys()) if rows else []
    features, _ = t1.select_feature_columns(columns, include_timestamps=False)

    # Resolution model on resolved (CP, FP, FA) vs unresolved (PC, APC); y = 1 means resolved.
    matrix, y_res, groups, dropped, _ = t1.build_arrays(rows, features, RESOLVED, UNRESOLVED)
    matrix, features, empty = t1.drop_empty_columns(matrix, features)
    splitter = GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=0)
    e = np.zeros(len(y_res))
    for tr, te in splitter.split(matrix, y_res, groups):
        model = _resolution_model(resolution_model)
        model.fit(matrix[tr], y_res[tr])
        e[te] = model.predict_proba(matrix[te])[:, 1]
    resolution_auc = float(roc_auc_score(y_res, e))

    # Labeled cohort L: the resolved rows, in the same order build_arrays kept them.
    kept = [r for r in rows if (r.get("tid") or "").strip()
            and (r.get(t1.TOI_DISPOSITION_COLUMN) or "").strip().upper() in RESOLVED + UNRESOLVED]
    states = np.array([(r.get(t1.TOI_DISPOSITION_COLUMN) or "").strip().upper() for r in kept])
    in_l = np.isin(states, RESOLVED)
    return {
        "digest": digest,
        "resolution_model": resolution_model,
        "features": features,
        "dropped_empty_features": empty,
        "resolution_model_oof_auc": resolution_auc,
        "X": matrix[in_l],
        "y": np.isin(states[in_l], POSITIVE).astype(int),
        "groups": groups[in_l],
        "e": e[in_l],
        "n_unresolved": int((~in_l).sum()),
    }


# ---------------------------------------------------------------- host-level sampling


def host_split(groups: np.ndarray, e: np.ndarray, gamma: float, rho: float,
               rng: np.random.Generator) -> np.ndarray:
    """Boolean mask of TOIs in R*.

    Hosts are drawn without replacement with probability proportional to
    mean(e)^gamma (Efraimidis-Spirakis keys), and added until R* holds rho of
    the TOIs. A host is never split across R* and U*. gamma = 0 is uniform.
    """
    hosts, inverse, counts = np.unique(groups, return_inverse=True, return_counts=True)
    host_e = np.bincount(inverse, weights=e) / counts
    weight = np.clip(host_e, 1e-9, None) ** gamma
    keys = rng.random(len(hosts)) ** (1.0 / weight)
    order = np.argsort(-keys)
    target = rho * len(groups)
    chosen = np.zeros(len(hosts), dtype=bool)
    total = 0
    for h in order:
        if total >= target:
            break
        # Take the host if that brings R* closer to the target than stopping here.
        if abs(total + counts[h] - target) <= abs(total - target):
            chosen[h] = True
            total += counts[h]
        else:
            break
    return chosen[inverse]


# ---------------------------------------------------------------- one replicate


def make_vetting(model: str, seed: int):
    if model == "lr":
        return t1.make_model()
    if model == "hgb":
        return HistGradientBoostingClassifier(random_state=seed)
    raise ValueError(f"unknown model {model!r}; use one of {MODELS}")


def _domain_weights(X_r: np.ndarray, X_u: np.ndarray, g_r: np.ndarray, g_u: np.ndarray, seed: int) -> np.ndarray:
    """w = p/(1-p) for R* rows, p = P(U* | x) from a host-grouped cross-fitted domain classifier."""
    X = np.vstack([X_r, X_u])
    d = np.r_[np.zeros(len(X_r)), np.ones(len(X_u))]
    g = np.r_[g_r, g_u]
    p = np.zeros(len(X))
    for tr, te in GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed).split(X, d, g):
        clf = t1.make_model()
        clf.fit(X[tr], d[tr])
        p[te] = clf.predict_proba(X[te])[:, 1]
    p_r = np.clip(p[: len(X_r)], 1e-6, 1 - 1e-6)
    return p_r / (1 - p_r)


def replicate(prep: dict, model: str, gamma: float, seed: int, rho: float = RHO) -> dict:
    rng = np.random.default_rng(seed)
    X, y, groups, e = prep["X"], prep["y"], prep["groups"], prep["e"]
    in_r = host_split(groups, e, gamma, rho, rng)
    X_r, y_r, g_r = X[in_r], y[in_r], groups[in_r]
    X_u, y_u, g_u = X[~in_r], y[~in_r], groups[~in_r]
    info = {"seed": seed, "n_r": int(in_r.sum()), "n_u": int((~in_r).sum()),
            "share_r": float(in_r.mean()), "pos_r": int(y_r.sum()), "pos_u": int(y_u.sum()),
            "mean_e_r": float(e[in_r].mean()), "mean_e_u": float(e[~in_r].mean())}
    if min(y_r.sum(), len(y_r) - y_r.sum(), y_u.sum(), len(y_u) - y_u.sum()) < MIN_PER_CLASS:
        return {**info, "valid": False}

    oof = np.zeros(len(y_r))
    fold_true = []
    for tr, te in GroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed).split(X_r, y_r, g_r):
        clf = make_vetting(model, seed)
        clf.fit(X_r[tr], y_r[tr])
        oof[te] = clf.predict_proba(X_r[te])[:, 1]
        fold_true.append(roc_auc_score(y_u, clf.predict_proba(X_u)[:, 1]))

    w = _domain_weights(X_r, X_u, g_r, g_u, seed)
    w_iw = w / w.mean()
    w_clip = np.minimum(w, np.percentile(w, 95))
    w_clip = w_clip / w_clip.mean()
    estimates = {
        "naive": float(roc_auc_score(y_r, oof)),
        "iw": float(roc_auc_score(y_r, oof, sample_weight=w_iw)),
        "iw_clip": float(roc_auc_score(y_r, oof, sample_weight=w_clip)),
    }
    true_auc = float(np.mean(fold_true))
    return {**info, "valid": True, "true_auc": true_auc, "estimates": estimates,
            "gap": estimates["naive"] - true_auc, "max_weight_iw": float(w_iw.max())}


@functools.lru_cache(maxsize=64)
def _replicates(path_str: str, expected: str, model: str, gamma: float, seed: int, n: int, rho: float,
                resolution_model: str = "lr") -> tuple:
    prep = prepare(path_str, expected, resolution_model)
    return tuple(replicate(prep, model, gamma, 1000 * seed + r, rho) for r in range(n))


def _interval(values: list[float]) -> list[float]:
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


# ---------------------------------------------------------------- runner contract


def run(task_id: str, params: dict, seed: int) -> dict:
    if task_id != TASK_ID:
        raise ValueError(f"task_id must be {TASK_ID!r}")
    model = params.get("model", "lr")
    estimator = params.get("estimator", "naive")
    gamma = float(params.get("gamma", 1))
    n = int(params.get("replicates", DEFAULT_REPLICATES))
    resolution_model = params.get("resolution_model", "lr")
    if resolution_model not in RESOLUTION_MODELS:
        raise ValueError(f"resolution_model must be one of {RESOLUTION_MODELS}")
    if model not in MODELS or estimator not in ESTIMATORS:
        raise ValueError(f"model must be one of {MODELS}, estimator one of {ESTIMATORS}")
    if gamma not in (0.0, 1.0, 2.0):
        raise ValueError("gamma must be 0, 1 or 2 (bench/PROTOCOL_TESS.md section 4)")

    path, expected = str(data_path()), expected_sha256()
    prep = prepare(path, expected, resolution_model)
    reps = _replicates(path, expected, model, gamma, seed, n, RHO, resolution_model)
    valid = [r for r in reps if r["valid"]]
    if not valid:
        raise RuntimeError("no valid replicate: a class is too rare in R* or U*")
    est = [r["estimates"][estimator] for r in valid]
    true = [r["true_auc"] for r in valid]
    err = [abs(a - b) for a, b in zip(est, true)]
    gap = [r["gap"] for r in valid]
    return {
        "metrics": {
            "abs_error": float(np.mean(err)),
            "estimate": float(np.mean(est)),
            "true_auc": float(np.mean(true)),
            "naive_auc": float(np.mean([r["estimates"]["naive"] for r in valid])),
            "gap": float(np.mean(gap)),
            "gap_low": _interval(gap)[0],
            "gap_high": _interval(gap)[1],
            "abs_error_low": _interval(err)[0],
            "abs_error_high": _interval(err)[1],
            "share_r": float(np.mean([r["share_r"] for r in valid])),
        },
        "replicates": n,
        "replicates_valid": len(valid),
        "replicate_seeds": [r["seed"] for r in reps],
        "data_sha256": prep["digest"],
        "resolution_model": resolution_model,
        "resolution_model_oof_auc": prep["resolution_model_oof_auc"],
        "framing": "semi-synthetic simulation inside the labeled cohort; not accuracy on real unresolved TOIs",
    }


# ---------------------------------------------------------------- oracle (proposed decision rule)

NO_CORRECTION = "no_correction"
PRACTICAL_THRESHOLD = 0.02   # bench/PROTOCOL_TESS.md section 5 (provisional)
ORACLE_TOLERANCE = 0.005     # top set: estimators within this mean |error| of the best


def candidates() -> list[str]:
    return [NO_CORRECTION] + [f"{m}_{e}" for m in MODELS for e in ESTIMATORS]


def build_oracle(seeds=(1, 2, 3, 4, 5), replicates: int = DEFAULT_REPLICATES) -> dict:
    """Pool every replicate of every benchmark seed and apply the decision rule.

    1. Pooled gap (lr, naive, gamma 1) over len(seeds) x replicates simulated splits.
    2. If the gap is below the practical threshold or its interval includes 0, the correct
       recommendation is "report resolved-set AUC as is": no_correction, or a naive estimator.
    3. Otherwise the correct recommendation is any correcting estimator within
       ORACLE_TOLERANCE of the lowest mean |error| (naive estimators are excluded).
    """
    path, expected = str(data_path()), expected_sha256()
    prep = prepare(path, expected)

    def pooled(model: str, gamma: float) -> list[dict]:
        return [r for s in seeds for r in _replicates(path, expected, model, gamma, s, replicates, RHO) if r["valid"]]

    gaps = np.array([r["gap"] for r in pooled("lr", 1.0)])
    se = float(gaps.std(ddof=1) / np.sqrt(len(gaps)))
    gap = {"mean": float(gaps.mean()), "se": se, "ci95": [float(gaps.mean() - 1.96 * se), float(gaps.mean() + 1.96 * se)],
           "replicate_range95": _interval(list(gaps)), "n": int(len(gaps))}
    control = np.array([r["gap"] for r in pooled("lr", 0.0)])
    control_mean = float(control.mean())

    table = {}
    for m in MODELS:
        reps = pooled(m, 1.0)
        for e in ESTIMATORS:
            err = np.array([abs(r["estimates"][e] - r["true_auc"]) for r in reps])
            bias = np.array([r["estimates"][e] - r["true_auc"] for r in reps])
            table[f"{m}_{e}"] = {"mean_abs_error": float(err.mean()), "mean_signed_error": float(bias.mean()),
                                 "n": int(len(err))}

    meaningful = gap["mean"] >= PRACTICAL_THRESHOLD and gap["ci95"][0] > 0

    # Nonlinear sensitivity arm (reported only, never changes the decision): same simulation with a
    # gradient-boosting resolution model, which can capture selection the linear model misses.
    sens_reps = [r for s in seeds for r in _replicates(path, expected, "lr", 1.0, s, replicates, RHO, "hgb") if r["valid"]]
    sens = np.array([r["gap"] for r in sens_reps])
    sens_se = float(sens.std(ddof=1) / np.sqrt(len(sens)))
    sensitivity = {
        "resolution_model": "hgb",
        "resolution_model_oof_auc": prepare(path, expected, "hgb")["resolution_model_oof_auc"],
        "mean_gap": float(sens.mean()), "se": sens_se,
        "ci95": [float(sens.mean() - 1.96 * sens_se), float(sens.mean() + 1.96 * sens_se)], "n": int(len(sens)),
    }
    sens_meaningful = sensitivity["mean_gap"] >= PRACTICAL_THRESHOLD and sensitivity["ci95"][0] > 0
    sensitivity["agrees_with_primary"] = sens_meaningful == meaningful
    sensitivity["note"] = ("reported only; if it disagrees with the primary decision, the claim must say the "
                           "linear mechanism may understate the selection effect")
    if meaningful:
        correcting = {k: v for k, v in table.items() if not k.endswith("_naive")}
        best = min(correcting, key=lambda k: correcting[k]["mean_abs_error"])
        top = sorted(k for k, v in correcting.items()
                     if v["mean_abs_error"] - correcting[best]["mean_abs_error"] <= ORACLE_TOLERANCE)
        decision = "overstated: recommend a correcting estimator"
    else:
        best, top = NO_CORRECTION, sorted([NO_CORRECTION] + [k for k in table if k.endswith("_naive")])
        decision = "not meaningfully overstated under this mechanism: report resolved-set AUC with its interval"
    return {
        "schema_version": "1.0",
        "status": "SEMI_SYNTHETIC_SIMULATION_NOT_REAL_UNRESOLVED_ACCURACY",
        "data_sha256": prep["digest"],
        "seeds": list(seeds), "replicates_per_seed": replicates,
        "resolution_model_oof_auc": prep["resolution_model_oof_auc"],
        "labeled_cohort": {"n": int(len(prep["y"])), "positive": int(prep["y"].sum()), "n_unresolved": prep["n_unresolved"]},
        "gap_gamma1_lr_naive": gap,
        "control_gamma0_mean_gap": control_mean,
        "control_within_bound": abs(control_mean) < 0.01,
        "sensitivity_nonlinear_resolution": sensitivity,
        "practical_threshold": PRACTICAL_THRESHOLD,
        "decision": decision,
        "best": best,
        "within_threshold": top,
        "candidates": candidates(),
        "estimator_table": table,
    }


# ---------------------------------------------------------------- cache creation


def fetch(out: Path, timeout: int = 600) -> str:
    """Download the full TOI table once and save the raw bytes; returns their sha256."""
    columns = sorted({"toi", "tid", t1.TOI_DISPOSITION_COLUMN, *t1.TIMESTAMP_COLUMNS,
                      *t1._discover_columns(timeout)})
    query = f"select {','.join(columns)} from {t1.TOI_TABLE}"
    url = f"{t1.TAP}?query={urllib.parse.quote(query)}&format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "FORGE-tess-bias/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TESS resolution-bias semi-synthetic runner.")
    p.add_argument("--fetch", action="store_true", help="download the TOI table to FORGE_TESS_CSV and print its hash")
    p.add_argument("--model", default="lr", choices=MODELS)
    p.add_argument("--estimator", default="naive", choices=ESTIMATORS)
    p.add_argument("--gamma", type=float, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    p.add_argument("--oracle", metavar="OUT", help="build the pooled oracle over seeds 1-5 and write it to OUT")
    a = p.parse_args(argv)
    if a.oracle:
        out = build_oracle(replicates=a.replicates)
        Path(a.oracle).parent.mkdir(parents=True, exist_ok=True)
        Path(a.oracle).write_text(json.dumps(out, indent=2) + "\n")
        print(json.dumps({k: out[k] for k in ("decision", "best", "within_threshold", "gap_gamma1_lr_naive",
                                                "control_gamma0_mean_gap", "control_within_bound")}, indent=2))
        return 0
    if a.fetch:
        digest = fetch(data_path())
        print(f"saved {data_path()} sha256={digest}\nPin it: export FORGE_TESS_SHA256={digest} "
              "and record it in the bench/PROTOCOL_TESS.md change log.")
        return 0
    out = run(TASK_ID, {"model": a.model, "estimator": a.estimator, "gamma": a.gamma, "replicates": a.replicates},
              a.seed)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
