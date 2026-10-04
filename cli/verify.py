"""Check a run's hash chain.

    python -m cli.verify <run_id> [--db results/ledger.db]
    python -m cli.verify <run_id> --jsonl <episode>/events.jsonl

Exit code 0 if the chain is intact, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json

from core.ledger import DEFAULT_PATH, Ledger, first_bad_seq


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify the hash chain of a FORGE run.")
    p.add_argument("run_id")
    p.add_argument("--db", default=DEFAULT_PATH, help="ledger path")
    p.add_argument("--jsonl", help="check an exported events.jsonl instead of a ledger database")
    args = p.parse_args(argv)

    if args.jsonl:
        with open(args.jsonl, encoding="utf-8") as f:
            events = sorted((e for e in map(json.loads, filter(str.strip, f)) if e.get("run_id") == args.run_id),
                            key=lambda e: e["seq"])
        source, count = args.jsonl, len(events)
        bad_seq = first_bad_seq(events) if events else None
        ok = bad_seq is None
    else:
        ledger = Ledger(args.db)
        source, count = args.db, len(ledger.read(args.run_id))
        ok, bad_seq = ledger.verify(args.run_id) if count else (False, None)
    if count == 0:
        print(f"run {args.run_id!r}: NOT FOUND (0 events) in {source}")
        return 1
    if ok:
        print(f"run {args.run_id!r}: chain OK, {count} events")
        return 0
    print(f"run {args.run_id!r}: CHAIN BROKEN at seq {bad_seq}, {count} events")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
