"""Combine the lite-benchmark seeds into one report.

    python bench/aggregate_lite.py            # reads results/bench-lite/seed-*/, writes report.md and report.json

Reads each seed-N/A and seed-N/B episode as recorded (failed, timed-out and budget_exhausted episodes
stay in), scores them against the pre-lock oracle and writes the paired comparison with the fixed claim
wording and labels from bench/PROTOCOL_TESS.md section 12.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT]

import report  # noqa: E402

DEFAULT_OUT = os.path.join(REPO_ROOT, "results", "bench-lite")
DEFAULT_ORACLE = os.path.join(REPO_ROOT, "results", "tess_prelock", "oracle.json")
DEFAULT_PRELOCK = os.path.join(REPO_ROOT, "results", "tess_prelock", "summary.json")
CLAIM = "in a lite benchmark (n={n} seeds), FORGE vs a single-agent baseline on this TESS task"


def _load(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def labels(prelock: Optional[dict]) -> list[str]:
    out = ["semi-synthetic"]
    if not (prelock and prelock.get("checks", {}).get("lockable") is True):
        out.append("protocol not lockable")
    return out


def collect(out_root: str, oracle: Optional[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    arms: dict[str, list[dict]] = {}
    seeds = []
    for name in sorted(os.listdir(out_root)):
        seed_dir = os.path.join(out_root, name)
        if not (name.startswith("seed-") and os.path.isdir(seed_dir)):
            continue
        seed = int(name.split("-", 1)[1])
        summary = _load(os.path.join(seed_dir, "summary.json")) or {}
        seeds.append({"seed": seed, "command": (_load(os.path.join(seed_dir, "command.json")) or {}).get("command"),
                      "outcomes": {a: e.get("outcome") for a, e in summary.get("episodes", {}).items()}})
        for arm in ("A", "B"):
            # A launch that crashed before the episode existed still scores as a failed attempt.
            m = report.episode_metrics(os.path.join(seed_dir, arm), oracle)
            m["arm"], m["seed"] = arm, seed
            m["outcome"] = summary.get("episodes", {}).get(arm, {}).get("outcome")
            arms.setdefault(arm, []).append(m)
    return arms, seeds


def render(cmp: dict, oracle: Optional[dict], prelock: Optional[dict], seeds: list[dict]) -> str:
    n = len(cmp["paired_seeds"])
    head = [f"# Lite benchmark: {CLAIM.format(n=n)}", "",
            f"**Labels: {', '.join(labels(prelock))}.** Results are on a semi-synthetic simulation built on the "
            "TESS TOI snapshot, not accuracy on real unresolved TOIs. No claim beyond this task and these seeds.", "",
            "- Budget per episode, same for both arms: see command.json and summary.json in each seed folder.",
            "- Cost: n/a unless both arms capture usage.",
            "- Failed, timed-out and budget_exhausted episodes are included; nothing was re-run.",
            "- Literature tooling was not provided to either arm; this compares the protocol (committed "
            "predictions, budget, ledger, approval gate), not citation quality.", "",
            "## Episodes", "", "| Seed | A outcome | B outcome | Command |", "|---|---|---|---|"]
    for s in seeds:
        head.append(f"| {s['seed']} | {s['outcomes'].get('A') or 'missing'} | {s['outcomes'].get('B') or 'missing'} | "
                    f"`{s['command'] or 'n/a'}` |")
    body = report.render_markdown(cmp, oracle).split("\n", 2)[2]  # drop the generic title
    return "\n".join(head) + "\n" + body


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Aggregate lite-benchmark seeds.")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--oracle", default=DEFAULT_ORACLE)
    p.add_argument("--prelock", default=DEFAULT_PRELOCK)
    a = p.parse_args(argv)
    oracle, prelock = _load(a.oracle), _load(a.prelock)
    arms, seeds = collect(a.out, oracle)
    if not seeds:
        raise SystemExit(f"no seed-N folders in {a.out}")
    cmp = report.compare(arms, "A", "B")
    md = render(cmp, oracle, prelock, seeds)
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"claim": CLAIM.format(n=len(cmp["paired_seeds"])), "labels": labels(prelock),
                   "cost": "n/a unless both arms capture usage", "seeds": seeds, "comparison": cmp}, f,
                  indent=2, default=str)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
