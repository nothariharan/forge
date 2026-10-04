"""P6 human-approval gate for experiments, enforced through the ledger.

The experimenter runs the preregistered command through this wrapper. It
blocks until a human resolves the gate (GATE_RESOLVED in the ledger, written
by the lab UI's Approve/Reject buttons or `python -m cli.approve`), and only
then executes the command. Without an approval the experiment never starts.

    python tools/forge_gate.py --run-id R --gate-id G1 -- \\
        .venv/bin/python tools/tess_resolution_shift.py --bootstrap 200 ...

FORGE_GATE_MODE=auto (set by bench/launch_arm_b.py) approves immediately and
records the approval as agent "harness", so benchmark runs never wait on a
human and never pretend one approved.

Only GATE_RESOLVED written by agent "human" counts (or "harness" in auto mode);
tools/forge_emit.py refuses to let agents write either.

Exit codes: the wrapped command's own code once approved; 3 if the human
denied it; 4 on timeout; 5 if the wrapped command is not an approved tool;
6 if the gate was never opened.

Why not Omnigent's own ASK: sub-agents run headless, and the root session's
ASK needs an attached interactive client; in scripted runs neither can be
answered (found live in runs live-exo-4 and live-exo-5).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ledger import Ledger  # noqa: E402

APPROVED_TOOLS = ("tools/tess_resolution_shift.py",)


def wait_for_decision(ledger: Ledger, run_id: str, gate_id: str, timeout: float, poll: float = 1.0,
                      trusted: tuple[str, ...] = ("human",)) -> str | None:
    """Return the first decision on gate_id written by a trusted agent. Resolutions
    from anyone else (e.g. an agent forging one) are ignored."""
    deadline = time.monotonic() + timeout
    after = 0
    while time.monotonic() < deadline:
        for e in ledger.read(run_id, after_seq=after):
            after = e["seq"]
            if (e["type"] == "GATE_RESOLVED" and e["payload"].get("gate_id") == gate_id
                    and e["agent"] in trusted):
                return e["payload"].get("status")
        time.sleep(poll)
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        print("usage: forge_gate.py --run-id R --gate-id G -- <command>", file=sys.stderr)
        return 2
    split = argv.index("--")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run-id", required=True)
    p.add_argument("--gate-id", required=True)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--db", default=None)
    args = p.parse_args(argv[:split])
    command = argv[split + 1:]

    if len(command) < 2 or command[1] not in APPROVED_TOOLS:
        print(f"FORGE_GATE_REFUSED: only {APPROVED_TOOLS} may run behind the gate")
        return 5

    ledger = Ledger(args.db) if args.db else Ledger()
    auto = os.environ.get("FORGE_GATE_MODE") == "auto"
    events = ledger.read(args.run_id)
    if not any(e["type"] == "GATE_OPENED" and e["payload"].get("gate_id") == args.gate_id for e in events):
        print(f"FORGE_GATE_REFUSED: gate {args.gate_id} was never opened in run {args.run_id}")
        return 6
    already = any(e["type"] == "GATE_RESOLVED" and e["payload"].get("gate_id") == args.gate_id for e in events)
    if auto and not already:
        # Matched benchmark (arm B): no human in the loop, same as arm A. Logged as
        # the harness, never as a human approval. An existing decision is honoured.
        from cli.approve import resolve
        resolve(ledger, args.run_id, args.gate_id, approve=True, via="benchmark-auto (FORGE_GATE_MODE=auto, no human)", agent="harness")
    trusted = ("human", "harness") if auto else ("human",)
    print(f"FORGE_GATE_WAITING run={args.run_id} gate={args.gate_id}: approve in the lab UI or `python -m cli.approve {args.run_id} {args.gate_id}`", flush=True)
    decision = wait_for_decision(ledger, args.run_id, args.gate_id, args.timeout, trusted=trusted)
    if decision is None:
        print(f"FORGE_GATE_TIMEOUT after {args.timeout:.0f}s")
        return 4
    if decision != "approved":
        print(f"FORGE_GATE_DENIED by human ({decision})")
        return 3
    print("FORGE_GATE_APPROVED, running the experiment", flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
