"""Handoff gate between FORGE agents and the ledger.

The director calls this once per handoff, before forwarding anything to the
next agent. It validates the payload against the ledger schema for the event
type and appends it with Ledger.append.

- Valid payload: the event is written, prints "FORGE_EMIT_OK ...", exits 0.
- Invalid payload (bad JSON, unknown type, schema failure): nothing of that
  type is written. An ERROR event records the rejection with the raw input
  (truncated), prints "FORGE_EMIT_REJECTED ...", exits 2.

The marker strings are read by the Omnigent handoff policy in
omnigent/forge/config.yaml, which blocks the next sys_session_send after a
rejection. So an invalid handoff cannot move forward even if the director
ignores the exit code.

Usage:
    python tools/forge_emit.py --run-id R --agent hypothesizer \\
        --type HYPOTHESIS_PROPOSED --payload '{"hid": "H1", ...}' --ai-generated
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ledger import Ledger, ValidationError  # noqa: E402

RAW_LIMIT = 2000


def _reject(ledger: Ledger, args: argparse.Namespace, raw: str, why: str) -> int:
    ledger.append(
        run_id=args.run_id,
        agent="system",
        type="ERROR",
        payload={
            "message": f"handoff rejected: {why}",
            "where": args.agent,
            "rejected_type": args.type,
            "raw": raw[:RAW_LIMIT],
        },
    )
    print(f"FORGE_EMIT_REJECTED type={args.type} agent={args.agent} reason={why}")
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run-id", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--payload", required=True, help="JSON object, or @path to a JSON file")
    p.add_argument("--refs", default=None, help="JSON object of ids (hid, eid, parent, gate_id)")
    p.add_argument("--ai-generated", action="store_true")
    p.add_argument("--db", default=None, help="ledger path (default: $FORGE_LEDGER_DB or results/ledger.db)")
    args = p.parse_args(argv)

    raw = Path(args.payload[1:]).read_text() if args.payload.startswith("@") else args.payload
    ledger = Ledger(args.db) if args.db else Ledger()

    try:
        payload = json.loads(raw)
        refs = json.loads(args.refs) if args.refs else None
    except json.JSONDecodeError as e:
        return _reject(ledger, args, raw, f"invalid JSON ({e.msg})")
    if not isinstance(payload, dict):
        return _reject(ledger, args, raw, "payload is not a JSON object")

    try:
        event = ledger.append(args.run_id, args.agent, args.type, payload,
                              refs=refs, ai_generated=args.ai_generated)
    except ValidationError as e:
        return _reject(ledger, args, raw, str(e).replace("\n", " ")[:300])

    print(f"FORGE_EMIT_OK seq={event['seq']} type={args.type} agent={args.agent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
