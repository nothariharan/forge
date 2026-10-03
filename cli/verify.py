"""Check a run's hash chain.

    python -m cli.verify <run_id> [--db results/ledger.db]

Exit code 0 if the chain is intact, 1 otherwise.
"""
from __future__ import annotations

import argparse

from core.ledger import DEFAULT_PATH, Ledger


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify the hash chain of a FORGE run.")
    p.add_argument("run_id")
    p.add_argument("--db", default=DEFAULT_PATH, help="ledger path")
    args = p.parse_args(argv)

    ledger = Ledger(args.db)
    count = len(ledger.read(args.run_id))
    if count == 0:
        print(f"run {args.run_id!r}: NOT FOUND (0 events) in {args.db}")
        return 1
    ok, bad_seq = ledger.verify(args.run_id)
    if ok:
        print(f"run {args.run_id!r}: chain OK, {count} events")
        return 0
    print(f"run {args.run_id!r}: CHAIN BROKEN at seq {bad_seq}, {count} events")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
