"""Oracle sweep: run every candidate on every seed and write oracle.json.

The oracle is the deterministic ground truth the benchmark scores against
(bench/PROTOCOL.md section 7). It runs once, outside both arms.

Spec file (JSON):

    {
      "task_id": 31,
      "metric": "auc",
      "direction": "maximize",          # or "minimize"
      "practical_threshold": 0.005,     # candidates within this of the best mean count as "top"
      "seeds": [1, 2, 3, 4, 5],
      "runner": "tools.openml_run:run", # module:function, see below
      "candidates": [{"id": "c1", "params": {...}}, ...]
    }

Runner contract (proposed; to match tools/openml_run.py once it exists):

    run(task_id, params: dict, seed: int) -> {"metrics": {name: value}, ...}

Raw results are appended to sweep_runs.jsonl as they finish, so an
interrupted sweep resumes where it stopped. Failed runs are recorded, never
dropped; a candidate with any failed seed is marked incomplete and cannot be
the oracle best.

Usage:
    python bench/oracle.py spec.json --out results/bench/<bench_id>
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Callable, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_KEYS = ("task_id", "metric", "direction", "practical_threshold", "seeds", "runner", "candidates")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    missing = [k for k in REQUIRED_KEYS if k not in spec]
    if missing:
        raise ValueError(f"spec is missing keys: {missing}")
    if spec["direction"] not in ("maximize", "minimize"):
        raise ValueError("direction must be 'maximize' or 'minimize'")
    ids = [c["id"] for c in spec["candidates"]]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate ids must be unique")
    if not spec["seeds"]:
        raise ValueError("seeds must not be empty")
    return spec


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resolve_runner(ref: str) -> Callable:
    module_name, _, func_name = ref.partition(":")
    if not func_name:
        raise ValueError("runner must look like 'module.path:function'")
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    return getattr(importlib.import_module(module_name), func_name)


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def _load_done(runs_path: str, digest: str) -> dict[tuple[str, int], dict]:
    done: dict[tuple[str, int], dict] = {}
    if not os.path.exists(runs_path):
        return done
    with open(runs_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            # Only reuse results produced under the identical spec.
            if rec.get("spec_hash") == digest:
                done[(rec["candidate"], rec["seed"])] = rec
    return done


def _finite_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _json_safe(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def sweep(spec: dict, out_dir: str, runner: Optional[Callable] = None, log=print) -> list[dict]:
    """Run all (candidate, seed) pairs not already recorded. Returns all records."""
    os.makedirs(out_dir, exist_ok=True)
    runs_path = os.path.join(out_dir, "sweep_runs.jsonl")
    digest = spec_hash(spec)
    runner = runner or resolve_runner(spec["runner"])
    done = _load_done(runs_path, digest)
    metric = spec["metric"]

    total = len(spec["candidates"]) * len(spec["seeds"])
    with open(runs_path, "a", encoding="utf-8") as f:
        for cand in spec["candidates"]:
            for seed in spec["seeds"]:
                key = (cand["id"], seed)
                if key in done:
                    continue
                rec = {"spec_hash": digest, "candidate": cand["id"], "seed": seed, "started_at": _now()}
                t0 = time.monotonic()
                try:
                    result = runner(spec["task_id"], cand.get("params", {}), seed)
                    value = (result or {}).get("metrics", {}).get(metric)
                    if value is None:
                        status = "missing_metric"
                    elif not _finite_number(value):
                        # A NaN would poison the candidate mean; record the run as failed instead.
                        status, value = "non_finite_metric", str(value)
                    else:
                        status = "ok"
                    rec.update(status=status, value=value, raw=result)
                except Exception as exc:
                    rec.update(status="error", value=None, error=f"{type(exc).__name__}: {exc}",
                               traceback=traceback.format_exc(limit=5))
                rec["wall_seconds"] = round(time.monotonic() - t0, 3)
                rec["finished_at"] = _now()
                f.write(json.dumps(_json_safe(rec), default=str, allow_nan=False) + "\n")
                f.flush()
                done[key] = rec
                log(f"[{len(done)}/{total}] {cand['id']} seed={seed} {rec['status']} {metric}={rec['value']}")
    return list(done.values())


def build_oracle(spec: dict, records: list[dict]) -> dict:
    by_cand: dict[str, dict[int, dict]] = {c["id"]: {} for c in spec["candidates"]}
    for rec in records:
        if rec["candidate"] in by_cand:
            by_cand[rec["candidate"]][rec["seed"]] = rec

    sign = 1 if spec["direction"] == "maximize" else -1
    table = []
    for cid, runs in by_cand.items():
        values = [runs[s]["value"] for s in spec["seeds"] if s in runs and runs[s]["status"] == "ok"]
        complete = len(values) == len(spec["seeds"])
        table.append({
            "candidate": cid,
            "complete": complete,
            "n_ok": len(values),
            "n_failed": sum(1 for s in spec["seeds"] if s in runs and runs[s]["status"] != "ok"),
            "n_missing": sum(1 for s in spec["seeds"] if s not in runs),
            "mean": statistics.fmean(values) if values else None,
            "sd": statistics.stdev(values) if len(values) > 1 else None,
            "per_seed": {str(s): runs[s]["value"] if s in runs else None for s in spec["seeds"]},
        })

    eligible = [row for row in table if row["complete"]]
    best = max(eligible, key=lambda r: sign * r["mean"]) if eligible else None
    within = []
    if best:
        thr = spec["practical_threshold"]
        within = [r["candidate"] for r in eligible if sign * (best["mean"] - r["mean"]) <= thr]
        for row in table:
            row["gap_to_best"] = None if row["mean"] is None else sign * (best["mean"] - row["mean"])

    return {
        "schema_version": "1.0",
        "created_at": _now(),
        "git_commit": _git_commit(),
        "spec_hash": spec_hash(spec),
        "task_id": spec["task_id"],
        "metric": spec["metric"],
        "direction": spec["direction"],
        "practical_threshold": spec["practical_threshold"],
        "seeds": spec["seeds"],
        "best": best["candidate"] if best else None,
        "within_threshold": within,
        "candidates_total": len(table),
        "candidates_complete": len(eligible),
        "table": sorted(table, key=lambda r: (r["mean"] is None, -sign * (r["mean"] or 0))),
        "notes": [
            "Top set = complete candidates whose mean is within practical_threshold of the best mean.",
            "Candidates with any failed or missing seed are listed but cannot be best.",
            "The oracle defines 'correct' only within this candidate space.",
        ],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the oracle sweep and write oracle.json.")
    parser.add_argument("spec")
    parser.add_argument("--out", required=True, help="bench directory, e.g. results/bench/<bench_id>")
    parser.add_argument("--aggregate-only", action="store_true", help="skip running, rebuild oracle.json from sweep_runs.jsonl")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    if args.aggregate_only:
        records = list(_load_done(os.path.join(args.out, "sweep_runs.jsonl"), spec_hash(spec)).values())
    else:
        records = sweep(spec, args.out)
    oracle = build_oracle(spec, records)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "oracle.json"), "w", encoding="utf-8") as f:
        json.dump(oracle, f, indent=2)
    print(f"best={oracle['best']} top={oracle['within_threshold']} "
          f"complete={oracle['candidates_complete']}/{oracle['candidates_total']}")
    return 0 if oracle["best"] is not None else 2


if __name__ == "__main__":
    sys.exit(main())
