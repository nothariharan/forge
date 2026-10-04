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
FIXTURE_CLAIM = ("smoke-scale run (n={n} seeds) of the lite benchmark protocol on a synthetic TESS-like fixture, "
                 "FORGE vs a single-agent baseline; not the TESS task and not a benchmark result")


def is_fixture(seeds: list[dict]) -> bool:
    """Any seed that did not run on the pinned NASA TOI snapshot."""
    return any(not str(s.get("data_ver") or "").startswith("nasa-toi@") for s in seeds)


def claim(seeds: list[dict], n: int) -> str:
    return (FIXTURE_CLAIM if is_fixture(seeds) else CLAIM).format(n=n)


def _load(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SETUP_KEYS = ("omni_version", "model", "snapshot_sha256", "code_commit")


def setup_consistent(seeds: list[dict]) -> bool:
    """All seeds ran on the same locked omni version, model, snapshot and code commit."""
    setups = [s.get("setup") for s in seeds]
    if not setups or any(not st for st in setups):
        return False
    return all(tuple(st.get(k) for k in SETUP_KEYS) == tuple(setups[0].get(k) for k in SETUP_KEYS) for st in setups)


def labels(prelock: Optional[dict], seeds: Optional[list[dict]] = None) -> list[str]:
    out = ["semi-synthetic", "preliminary"]
    if seeds and is_fixture(seeds):
        out[0] = "synthetic fixture, not TESS data"
    if not (prelock and prelock.get("checks", {}).get("lockable") is True):
        out.append("protocol not lockable")
    if seeds is not None and not setup_consistent(seeds):
        out.append("setup differs across seeds")
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
        command = _load(os.path.join(seed_dir, "command.json")) or {}
        import run_lite_seed  # the same scan the runner uses, re-run so older runs get the full file list
        seeds.append({"seed": seed, "command": command.get("command"), "setup": command.get("lock"),
                      "data_ver": command.get("data_ver"), "hidden": command.get("hidden_during_episodes"),
                      "oracle_mentions": {a: run_lite_seed.leak_check(os.path.join(seed_dir, a), f"lite-{a}-{seed}")
                                          for a in summary.get("episodes", {})},
                      "outcomes": {a: e.get("outcome") for a, e in summary.get("episodes", {}).items()}})
        for arm in ("A", "B"):
            # A launch that crashed before the episode existed still scores as a failed attempt.
            m = report.episode_metrics(os.path.join(seed_dir, arm), oracle)
            m["arm"], m["seed"] = arm, seed
            m["outcome"] = summary.get("episodes", {}).get(arm, {}).get("outcome")
            arms.setdefault(arm, []).append(m)
    return arms, seeds


def hidden_line(seeds: list[dict]) -> str:
    hidden = sorted({p for s in seeds for p in (s.get("hidden") or [])})
    if hidden:
        return f"moved out of reach while agents ran ({', '.join(hidden)})."
    return ("not hidden; it was kept outside the repository, but agents ran without a sandbox and could in "
            "principle have read it.")


def render(cmp: dict, oracle: Optional[dict], prelock: Optional[dict], seeds: list[dict]) -> str:
    n = len(cmp["paired_seeds"])
    data_line = ("Results are on a synthetic TESS-like fixture (tests/tess_fixture.py), not the TESS snapshot; they show "
                 "how the two arms run the protocol, not anything about TESS." if is_fixture(seeds) else
                 "Results are on a semi-synthetic simulation built on the TESS TOI snapshot, not accuracy on real "
                 "unresolved TOIs.")
    head = [f"# Lite benchmark: {claim(seeds, n)}", "",
            f"**Labels: {', '.join(labels(prelock, seeds))}.** {data_line} No claim beyond this task and these seeds.", "",
            "- Budget per episode, same for both arms: see command.json and summary.json in each seed folder.",
            "- Cost: n/a (usage is not captured).",
            "- Not lockable or preliminary means no correctness or speedup claim is made from these numbers.",
            "- Failed, timed-out and budget_exhausted episodes are included; nothing was re-run.",
            "- Literature tooling was not provided to either arm; this compares the protocol (committed "
            "predictions, budget, ledger, approval gate), not citation quality.", "",
            "- Arm B's P6 gate is auto-approved by the harness (no human in either arm).",
            f"- Ground truth during the episodes: {hidden_line(seeds)} Agent logs, events and arm B handoff files "
            "are scanned for oracle mentions.", "",
            "## Episodes", "", "| Seed | A outcome | B outcome | Oracle mentions in agent output | Command |",
            "|---|---|---|---|---|"]
    for s in seeds:
        mentions = {a: m for a, m in (s.get("oracle_mentions") or {}).items() if m}
        head.append(f"| {s['seed']} | {s['outcomes'].get('A') or 'missing'} | {s['outcomes'].get('B') or 'missing'} | "
                    f"{mentions or 'none'} | `{s['command'] or 'n/a'}` |")
    head += ["", "## Setup (from each seed's command.json)", "", "| Seed | omni | model | code commit | snapshot |",
             "|---|---|---|---|---|"]
    for s in seeds:
        st = s.get("setup") or {}
        head.append(f"| {s['seed']} | {st.get('omni_version', 'n/a')} | {st.get('model', 'n/a')} | "
                    f"{(st.get('code_commit') or 'n/a')[:12]} | {(st.get('snapshot_sha256') or 'n/a')[:12]} |")
    head.append("")
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
        json.dump({"claim": claim(seeds, len(cmp["paired_seeds"])), "labels": labels(prelock, seeds),
                   "cost": "n/a: usage is not captured", "seeds": seeds, "comparison": cmp}, f,
                  indent=2, default=str)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
