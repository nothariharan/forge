"""Resolve a pending P6 gate from the terminal: `forge approve`.

    python -m cli.approve <run_id> <gate_id> [--deny] [--db PATH]

Writes GATE_RESOLVED (agent "human") copying the gate's action and risk from
its GATE_OPENED event. tools/forge_gate.py is waiting on exactly this event.
"""
from __future__ import annotations

import argparse
import sys

from core.ledger import Ledger


def resolve(ledger: Ledger, run_id: str, gate_id: str, approve: bool, via: str, agent: str = "human") -> dict:
    events = ledger.read(run_id)
    opened = next((e for e in reversed(events) if e["type"] == "GATE_OPENED" and e["payload"].get("gate_id") == gate_id), None)
    if opened is None:
        raise SystemExit(f"no GATE_OPENED for {gate_id} in run {run_id}")
    if any(e["type"] == "GATE_RESOLVED" and e["payload"].get("gate_id") == gate_id for e in events):
        raise SystemExit(f"{gate_id} is already resolved")
    p = opened["payload"]
    payload = {"gate_id": gate_id, "action": p.get("action", ""), "risk": p.get("risk", "unknown"),
               "status": "approved" if approve else "denied", "policy": p.get("policy", "P6"), "resolved_via": via}
    return ledger.append(run_id, agent, "GATE_RESOLVED", payload, refs={"gate_id": gate_id})


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("run_id")
    a.add_argument("gate_id")
    a.add_argument("--deny", action="store_true")
    a.add_argument("--db", default=None)
    args = a.parse_args(argv)
    ledger = Ledger(args.db) if args.db else Ledger()
    e = resolve(ledger, args.run_id, args.gate_id, not args.deny, via="cli")
    print(f"{args.gate_id} {e['payload']['status']} (seq {e['seq']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
