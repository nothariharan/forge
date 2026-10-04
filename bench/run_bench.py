"""Run the matched A-vs-B benchmark end to end and write the report.

For each seed it runs one arm A episode (single agent) and one arm B episode
(FORGE), alternating which arm goes first (A1 B1, B2 A2, A3 B3, ...) so time of
day and API load do not always favor one arm. Then it builds the oracle if an
oracle spec is given, and runs bench/report.py, which computes every metric,
the throughput multiplier and its interval from the raw episode files.

    python bench/run_bench.py --spec spec.json --bench-id adult-v1 --seeds 1 2 3 4 5 \
        [--oracle-spec oracle_spec.json] [--arms A B] [--dry-run]

Episodes go to results/bench/<bench_id>/<arm>/seed-<n>/. An episode folder that
already has a manifest is skipped, so an interrupted benchmark can be resumed
by running the same command again. Every launch, including failures, is listed
in results/bench/<bench_id>/bench_manifest.json.

The question-dependent values (spec, oracle candidates, seeds, budget) come
from the frozen protocol. Do not run this for real before the protocol is
locked: a multiplier from an unfrozen protocol is not evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT]

import launch_arm_a  # noqa: E402
import launch_arm_b  # noqa: E402
import oracle  # noqa: E402
import report  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def run_order(seeds: list[int], arms: list[str]) -> list[tuple[int, str]]:
    order = []
    for i, seed in enumerate(seeds):
        pair = list(arms) if i % 2 == 0 else list(reversed(arms))
        order += [(seed, arm) for arm in pair]
    return order


def run_bench(spec: dict, bench_id: str, seeds: list[int], arms: list[str] = ("A", "B"),
              out_root: str = os.path.join(REPO_ROOT, "results", "bench"), oracle_spec: Optional[str] = None,
              arm_a_cmd: str = launch_arm_a.DEFAULT_AGENT_CMD, arm_b_cmd: str = launch_arm_b.DEFAULT_AGENT_CMD,
              model: Optional[str] = None, dry_run: bool = False) -> dict:
    bench_dir = os.path.join(out_root, bench_id)
    os.makedirs(bench_dir, exist_ok=True)
    manifest_path = os.path.join(bench_dir, "bench_manifest.json")
    log = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {
        "bench_id": bench_id, "created_at": _now(), "git_commit": _git_commit(), "spec": spec, "seeds": seeds,
        "arms": list(arms), "model": model, "launches": [],
    }

    for seed, arm in run_order(seeds, list(arms)):
        episode = os.path.join(bench_dir, arm, f"seed-{seed}")
        if os.path.exists(os.path.join(episode, "manifest.json")):
            print(f"skip {arm} seed {seed}: already has an episode")
            continue
        entry = {"arm": arm, "seed": seed, "episode": os.path.relpath(episode, bench_dir), "started_at": _now()}
        try:
            if arm == "A":
                rec = launch_arm_a.launch(spec, seed, episode, run_id=f"{bench_id}-A-{seed}", model=model,
                                          agent_cmd=arm_a_cmd, dry_run=dry_run)
            else:
                rec = launch_arm_b.launch(spec, seed, episode, run_id=f"{bench_id}-B-{seed}", model=model,
                                          agent_cmd=arm_b_cmd, dry_run=dry_run)
            entry["outcome"] = rec.get("outcome", "dry_run" if dry_run else None)
        except (Exception, SystemExit) as exc:  # a failed launch is recorded, never silently dropped
            entry.update(outcome="launch_failed", error=f"{type(exc).__name__}: {exc}",
                         traceback=traceback.format_exc(limit=5))
        entry["finished_at"] = _now()
        log["launches"].append(entry)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2)
        print(f"{arm} seed {seed}: {entry['outcome']}")

    if oracle_spec and not dry_run:
        ospec = oracle.load_spec(oracle_spec)
        built = oracle.build_oracle(ospec, oracle.sweep(ospec, bench_dir))
        with open(os.path.join(bench_dir, "oracle.json"), "w", encoding="utf-8") as f:
            json.dump(built, f, indent=2)

    result = {"bench_dir": bench_dir, "launches": log["launches"]}
    if not dry_run and set(arms) == {"A", "B"}:
        report.main([bench_dir, "--baseline", "A", "--treatment", "B"])
        result["report"] = os.path.join(bench_dir, "report.md")
    return result


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run the matched A-vs-B benchmark and write the report.")
    p.add_argument("--spec", required=True, help="task spec shared by both arms (see bench/launch_arm_a.py)")
    p.add_argument("--bench-id", required=True)
    p.add_argument("--seeds", type=int, nargs="+", required=True)
    p.add_argument("--arms", nargs="+", default=["A", "B"], choices=["A", "B"])
    p.add_argument("--oracle-spec", help="oracle sweep spec (see bench/oracle.py); needed to score correctness")
    p.add_argument("--out-root", default=os.path.join(REPO_ROOT, "results", "bench"))
    p.add_argument("--model", help="model ID used by both arms, recorded in every manifest")
    p.add_argument("--arm-a-cmd", default=launch_arm_a.DEFAULT_AGENT_CMD)
    p.add_argument("--arm-b-cmd", default=launch_arm_b.DEFAULT_AGENT_CMD)
    p.add_argument("--dry-run", action="store_true", help="initialise every episode without starting agents")
    a = p.parse_args(argv)
    run_bench(launch_arm_a.load_spec(a.spec), a.bench_id, a.seeds, a.arms, a.out_root, a.oracle_spec,
              a.arm_a_cmd, a.arm_b_cmd, a.model, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
