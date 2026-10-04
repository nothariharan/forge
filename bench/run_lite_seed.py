"""Run one seed of the lite benchmark: arm A and arm B on the TESS task, same budget.

Lite benchmark (bench/PROTOCOL_TESS.md section 12): seeds 1-3, run in parallel on different
machines (Akshat seed 1, Ish seed 2, Hari seed 3). Each machine runs:

    python bench/run_lite_seed.py --seed 1

and commits results/bench-lite/seed-1/. Then anyone runs bench/aggregate_lite.py.

What it does:
- Refuses to start unless the TESS snapshot is pinned (spec data_ver) and the cached file matches
  that hash, so every machine runs on the same data.
- Refuses to overwrite an existing seed folder: episodes are never re-run for a nicer result.
- Runs both arms through the shared launchers (same timeout, close and cleanup code). The order
  alternates by seed (odd: A then B, even: B then A).
- Keeps failed, timed-out and budget_exhausted episodes; a launch that crashes is recorded too.
- Writes, in results/bench-lite/seed-N/:
    A/ and B/      full episode folders (events.jsonl, ledger.db, logs, manifest, answer, report)
    command.json   the exact command, git commit, Python, host and FORGE_* settings used
    summary.json   per-arm outcome and metrics, scored against the pre-lock oracle
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT, os.path.join(REPO_ROOT, "tools")]

import launch_arm_a  # noqa: E402
import launch_arm_b  # noqa: E402
import report  # noqa: E402

DEFAULT_SPEC = os.path.join(BENCH_DIR, "specs", "tess_resolution_bias.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "results", "bench-lite")
DEFAULT_ORACLE = os.path.join(REPO_ROOT, "results", "tess_prelock", "oracle.json")
FRAMING = ("semi-synthetic simulation on the TESS TOI snapshot; lite benchmark (n=3 seeds), FORGE vs a "
           "single-agent baseline on this TESS task; not accuracy on real unresolved TOIs")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> Optional[str]:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def check_snapshot(spec: dict) -> str:
    """The pinned hash from the spec, after checking the cached file matches it."""
    import tess_bias_run as tb
    sha = spec.get("data_ver", "").split("@", 1)[-1]
    if len(sha) != 64:
        raise SystemExit("the TESS snapshot is not pinned (spec data_ver); run `python tools/tess_prelock.py` "
                         "or pull the commit that pins it")
    tb.load_rows(tb.data_path(), sha)  # raises if the cached file is missing or differs
    return sha


def arm_order(seed: int, arms: list[str]) -> list[str]:
    return list(arms) if seed % 2 == 1 else list(reversed(arms))


def run_seed(seed: int, spec: dict, out_root: str = DEFAULT_OUT, oracle_path: str = DEFAULT_ORACLE,
             arms: tuple[str, ...] = ("A", "B"), model: Optional[str] = None,
             arm_a_cmd: str = launch_arm_a.DEFAULT_AGENT_CMD, arm_b_cmd: str = launch_arm_b.DEFAULT_AGENT_CMD,
             argv: Optional[list[str]] = None) -> dict:
    sha = check_snapshot(spec)
    seed_dir = os.path.join(out_root, f"seed-{seed}")
    if os.path.exists(seed_dir):
        raise SystemExit(f"{seed_dir} already exists; episodes are never re-run. Delete it only if no agent "
                         "ever started there, and say so in the results README.")
    os.makedirs(seed_dir)
    command = {
        "command": " ".join(shlex.quote(a) for a in (argv or sys.argv)),
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(), "platform": platform.platform(), "host": socket.gethostname(),
        "started_at": _now(), "seed": seed, "model": model, "snapshot_sha256": sha,
        "agent_cmds": {"A": arm_a_cmd, "B": arm_b_cmd},
        "env": {k: v for k, v in os.environ.items() if k.startswith("FORGE_")},
    }
    with open(os.path.join(seed_dir, "command.json"), "w", encoding="utf-8") as f:
        json.dump(command, f, indent=2)

    oracle = json.load(open(oracle_path)) if os.path.exists(oracle_path) else None
    episodes = {}
    for arm in arm_order(seed, list(arms)):
        ep = os.path.join(seed_dir, arm)
        entry = {"arm": arm, "started_at": _now()}
        try:
            if arm == "A":
                rec = launch_arm_a.launch(spec, seed, ep, run_id=f"lite-A-{seed}", model=model, agent_cmd=arm_a_cmd)
            else:
                rec = launch_arm_b.launch(spec, seed, ep, run_id=f"lite-B-{seed}", model=model, agent_cmd=arm_b_cmd)
            entry.update(outcome=rec.get("outcome"), failure_reason=rec.get("failure_reason"),
                         timed_out=rec.get("timed_out"), returncode=rec.get("returncode"))
            entry["metrics"] = report.episode_metrics(ep, oracle)
        except (Exception, SystemExit) as exc:  # a crashed launch stays in the record, never dropped
            entry.update(outcome="launch_failed", error=f"{type(exc).__name__}: {exc}",
                         traceback=traceback.format_exc(limit=5))
        entry["finished_at"] = _now()
        episodes[arm] = entry
        print(f"seed {seed} arm {arm}: {entry['outcome']}")

    summary = {
        "framing": FRAMING, "seed": seed, "snapshot_sha256": sha,
        "oracle": os.path.relpath(oracle_path, REPO_ROOT) if oracle else None,
        "oracle_answer": oracle and {"best": oracle["best"], "within_threshold": oracle["within_threshold"]},
        "budget": {"wall_clock_minutes": spec.get("wall_clock_minutes"),
                   "max_experiments": spec.get("max_experiments"),
                   "usd_cap": spec.get("usd_cap")},
        "cost": "n/a unless both arms capture usage",
        "episodes": episodes, "finished_at": _now(),
    }
    with open(os.path.join(seed_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run one lite-benchmark seed (arm A and arm B).")
    p.add_argument("--seed", type=int, required=True, choices=[1, 2, 3])
    p.add_argument("--spec", default=DEFAULT_SPEC)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--oracle", default=DEFAULT_ORACLE)
    p.add_argument("--arms", nargs="+", default=["A", "B"], choices=["A", "B"])
    p.add_argument("--model", help="model ID used by both arms (recorded)")
    p.add_argument("--arm-a-cmd", default=launch_arm_a.DEFAULT_AGENT_CMD)
    p.add_argument("--arm-b-cmd", default=launch_arm_b.DEFAULT_AGENT_CMD)
    a = p.parse_args(argv)
    run_seed(a.seed, launch_arm_a.load_spec(a.spec), a.out, a.oracle, tuple(a.arms), a.model,
             a.arm_a_cmd, a.arm_b_cmd, argv=[sys.executable, *(argv if argv is not None else sys.argv)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
