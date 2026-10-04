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
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT, os.path.join(REPO_ROOT, "tools")]

import launch_arm_a  # noqa: E402
import launch_arm_b  # noqa: E402
import redact  # noqa: E402
import report  # noqa: E402

DEFAULT_SPEC = os.path.join(BENCH_DIR, "specs", "tess_resolution_bias.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "results", "bench-lite")
DEFAULT_ORACLE = os.path.join(REPO_ROOT, "results", "tess_prelock", "oracle.json")
DEFAULT_LOCK = os.path.join(BENCH_DIR, "specs", "lite_lock.json")
LOCK_KEYS = ("omni_version", "model", "snapshot_sha256", "code_commit")
FRAMING = ("semi-synthetic simulation on the TESS TOI snapshot; lite benchmark (n=3 seeds), FORGE vs a "
           "single-agent baseline on this TESS task; not accuracy on real unresolved TOIs")
FIXTURE_FRAMING = ("synthetic TESS-like fixture (tests/tess_fixture.py), NOT the TESS snapshot; smoke-scale run of the "
                   "lite benchmark protocol, FORGE vs a single-agent baseline; no claim about TESS")
# Ground truth the agents must not see while an episode runs (both arms run inside the repository).
HIDDEN_DURING_EPISODES = (os.path.join(REPO_ROOT, "results", "tess_prelock"),)
LEAK_MARKERS = ("--oracle", "tess_prelock", "oracle.json")
VENV_BIN = os.path.join(REPO_ROOT, ".venv", "bin")


def framing(spec: dict) -> str:
    return FRAMING if str(spec.get("data_ver", "")).startswith("nasa-toi@") else FIXTURE_FRAMING


@contextmanager
def hidden(paths=None):
    """Move ground-truth files out of the repository while the episodes run, then restore them."""
    paths = HIDDEN_DURING_EPISODES if paths is None else paths
    stash = tempfile.mkdtemp(prefix="forge-hidden-")
    moved = []
    try:
        for i, path in enumerate(paths):
            if os.path.exists(path):
                dest = os.path.join(stash, str(i))
                shutil.move(path, dest)
                moved.append((dest, path))
        yield [p for _, p in moved]
    finally:
        for dest, path in moved:
            shutil.move(dest, path)
        shutil.rmtree(stash, ignore_errors=True)


def leak_check(episode_dir: str) -> list[str]:
    """Agent output that mentions the oracle or its files (a sign the ground truth was looked up)."""
    hits = []
    for name in ("agent_stdout.log", "agent_stderr.log"):
        path = os.path.join(episode_dir, name)
        if os.path.exists(path):
            text = open(path, encoding="utf-8", errors="replace").read()
            hits += [f"{name}: {m}" for m in LEAK_MARKERS if m in text]
    return hits


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> Optional[str]:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def package_versions() -> dict:
    import tess_bias_run as tb
    return tb.package_versions()


def check_snapshot(spec: dict) -> str:
    """The pinned hash from the spec, after checking the cached file matches it."""
    import tess_bias_run as tb
    sha = spec.get("data_ver", "").split("@", 1)[-1]
    if len(sha) != 64:
        raise SystemExit("the TESS snapshot is not pinned (spec data_ver); run `python tools/tess_prelock.py` "
                         "or pull the commit that pins it")
    tb.load_rows(tb.data_path(), sha)  # raises if the cached file is missing or differs
    return sha


def omni_version() -> str:
    """The installed Omnigent version, from `omni --version`."""
    try:
        out = subprocess.run(["omni", "--version"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"cannot read the omni version ({exc}); is omni installed and on PATH?")
    m = re.search(r"\d+\.\d+\.\d+\S*", out)
    if not m:
        raise SystemExit(f"cannot parse the omni version from: {out!r}")
    return m.group(0)


def _lock_rel(lock_path: str) -> str:
    return os.path.relpath(os.path.abspath(lock_path), REPO_ROOT)


def tree_clean() -> bool:
    """No modified tracked files (untracked files such as other seeds' results are allowed)."""
    return _git("status", "--porcelain", "--untracked-files=no") == ""


def code_matches(lock: dict, lock_path: str) -> bool:
    paths = list(lock["code_paths"])
    rel = _lock_rel(lock_path)
    if not rel.startswith(".."):
        paths.append(f":(exclude){rel}")
    res = subprocess.run(["git", "diff", "--quiet", lock["code_commit"], "HEAD", "--", *paths], cwd=REPO_ROOT,
                         capture_output=True, text=True)
    if res.returncode > 1:  # e.g. the locked commit is not in a shallow clone
        raise SystemExit(f"cannot compare with the locked commit {lock['code_commit'][:12]}: {res.stderr.strip()}")
    return res.returncode == 0


def write_lock(lock_path: str, spec: dict, model: str) -> dict:
    if not model:
        raise SystemExit("--write-lock needs --model")
    if not tree_clean():
        raise SystemExit("the git tree has uncommitted changes; commit or stash them before writing the lock")
    lock = json.load(open(lock_path)) if os.path.exists(lock_path) else {}
    lock.update(omni_version=omni_version(), model=model, snapshot_sha256=check_snapshot(spec),
                code_commit=_git("rev-parse", "HEAD"))
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
        f.write("\n")
    return lock


def check_lock(lock: dict, lock_path: str, sha: str, model: Optional[str]) -> dict:
    """Every seed runs on the same omni version, model, clean code commit and snapshot."""
    missing = [k for k in LOCK_KEYS if lock.get(k, "PIN") == "PIN"]
    if missing:
        raise SystemExit(f"{_lock_rel(lock_path)} is not written yet ({', '.join(missing)}); "
                         "run `python bench/run_lite_seed.py --write-lock --model <id>` once and commit it")
    problems = []
    if not tree_clean():
        problems.append("the git tree has uncommitted changes")
    if not code_matches(lock, lock_path):
        problems.append(f"code under {lock['code_paths']} differs from the locked commit {lock['code_commit'][:12]}")
    if sha != lock["snapshot_sha256"]:
        problems.append(f"snapshot {sha[:12]} != locked {lock['snapshot_sha256'][:12]}")
    if model and model != lock["model"]:
        problems.append(f"--model {model} != locked {lock['model']}")
    found = omni_version()
    if found != lock["omni_version"]:
        problems.append(f"omni {found} != locked {lock['omni_version']}")
    if problems:
        raise SystemExit("setup does not match the lite lock: " + "; ".join(problems))
    return {**{k: lock[k] for k in LOCK_KEYS}, "omni_version_found": found, "head_commit": _git("rev-parse", "HEAD")}


def arm_order(seed: int, arms: list[str]) -> list[str]:
    return list(arms) if seed % 2 == 1 else list(reversed(arms))


def run_seed(seed: int, spec: dict, out_root: str = DEFAULT_OUT, oracle_path: str = DEFAULT_ORACLE,
             arms: tuple[str, ...] = ("A", "B"), model: Optional[str] = None,
             arm_a_cmd: str = launch_arm_a.DEFAULT_AGENT_CMD, arm_b_cmd: str = launch_arm_b.DEFAULT_AGENT_CMD,
             argv: Optional[list[str]] = None, lock_path: str = DEFAULT_LOCK) -> dict:
    sha = check_snapshot(spec)
    lock = json.load(open(lock_path)) if os.path.exists(lock_path) else {}
    setup = check_lock(lock, lock_path, sha, model)
    model = setup["model"]
    seed_dir = os.path.join(out_root, f"seed-{seed}")
    if os.path.exists(seed_dir):
        raise SystemExit(f"{seed_dir} already exists; episodes are never re-run. Delete it only if no agent "
                         "ever started there, and say so in the results README.")
    os.makedirs(seed_dir)
    command = {
        "command": redact.redact_text(" ".join(shlex.quote(a) for a in (argv or sys.argv))),
        "git_commit": setup["head_commit"], "git_dirty": False, "lock": setup,
        "python": platform.python_version(), "packages": package_versions(), "platform": platform.platform(), "host": socket.gethostname(),
        "started_at": _now(), "seed": seed, "model": model, "data_ver": spec.get("data_ver"), "snapshot_sha256": sha,
        "agent_cmds": {"A": redact.redact_text(arm_a_cmd), "B": redact.redact_text(arm_b_cmd)},
        "env": redact.recorded_env(os.environ),
        "cost": "n/a: usage is not captured",
    }
    with open(os.path.join(seed_dir, "command.json"), "w", encoding="utf-8") as f:
        json.dump(command, f, indent=2)

    oracle = json.load(open(oracle_path)) if os.path.exists(oracle_path) else None
    old_path = os.environ.get("PATH", "")
    if os.path.isdir(VENV_BIN):  # both arms' `python` / `.venv/bin/python` resolve to the same pinned environment
        os.environ["PATH"] = VENV_BIN + os.pathsep + old_path
    command["agent_python"] = shutil.which("python")
    episodes = {}
    with hidden() as hidden_paths:
        command["hidden_during_episodes"] = [os.path.relpath(p, REPO_ROOT) for p in hidden_paths]
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
            except (Exception, SystemExit) as exc:  # a crashed launch stays in the record, never dropped
                entry.update(outcome="launch_failed", error=f"{type(exc).__name__}: {exc}",
                             traceback=traceback.format_exc(limit=5))
            entry["finished_at"] = _now()
            episodes[arm] = entry
            print(f"seed {seed} arm {arm}: {entry['outcome']}")
    os.environ["PATH"] = old_path
    for arm, entry in episodes.items():  # scored after the ground truth is back in place
        ep = os.path.join(seed_dir, arm)
        entry["metrics"] = report.episode_metrics(ep, oracle)
        entry["oracle_mentions"] = leak_check(ep)
    with open(os.path.join(seed_dir, "command.json"), "w", encoding="utf-8") as f:
        json.dump(command, f, indent=2)

    summary = {
        "framing": framing(spec), "data_ver": spec.get("data_ver"), "seed": seed, "snapshot_sha256": sha,
        "oracle": os.path.relpath(oracle_path, REPO_ROOT) if oracle else None,
        "oracle_answer": oracle and {"best": oracle["best"], "within_threshold": oracle["within_threshold"]},
        "budget": {"wall_clock_minutes": spec.get("wall_clock_minutes"),
                   "max_experiments": spec.get("max_experiments"),
                   "usd_cap": spec.get("usd_cap")},
        "setup": setup,
        "cost": "n/a: usage is not captured",
        "episodes": episodes, "finished_at": _now(),
    }
    with open(os.path.join(seed_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run one lite-benchmark seed (arm A and arm B).")
    p.add_argument("--seed", type=int, choices=[1, 2, 3])
    p.add_argument("--lock", default=DEFAULT_LOCK)
    p.add_argument("--write-lock", action="store_true",
                   help="record the current omni version, --model, snapshot and clean HEAD in the lock file, then exit")
    p.add_argument("--spec", default=DEFAULT_SPEC)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--oracle", default=DEFAULT_ORACLE)
    p.add_argument("--arms", nargs="+", default=["A", "B"], choices=["A", "B"])
    p.add_argument("--model", help="model ID used by both arms; defaults to the locked model")
    p.add_argument("--arm-a-cmd", default=launch_arm_a.DEFAULT_AGENT_CMD)
    p.add_argument("--arm-b-cmd", default=launch_arm_b.DEFAULT_AGENT_CMD)
    a = p.parse_args(argv)
    spec = launch_arm_a.load_spec(a.spec)
    if a.write_lock:
        print(json.dumps(write_lock(a.lock, spec, a.model), indent=2))
        print(f"commit {_lock_rel(a.lock)} and merge it before any seed runs")
        return 0
    if a.seed is None:
        p.error("--seed is required")
    run_seed(a.seed, spec, a.out, a.oracle, tuple(a.arms), a.model, a.arm_a_cmd, a.arm_b_cmd,
             argv=[sys.executable, *(argv if argv is not None else sys.argv)], lock_path=a.lock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
