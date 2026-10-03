"""Append-only, hash-chained event ledger on SQLite. See LEDGER.md."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core import schemas
from core.schemas import AGENTS, EVENT_TYPES, SCHEMA_VERSION, ValidationError  # noqa: F401 (re-exported)

DEFAULT_PATH = os.environ.get("FORGE_LEDGER_DB", "results/ledger.db")
GENESIS_HASH = "GENESIS"  # prev_hash of the first event in a run (same as bench/arm_a.py)
_LEGACY_GENESIS = "0" * 64  # also accepted by verify; the shared schema allows both
OPTIONAL_FIELDS = {"refs"}  # left out of the event (and its hash) when empty
FIELDS = ("schema_version", "seq", "ts", "run_id", "agent", "type", "refs", "payload", "ai_generated", "prev_hash", "hash")

_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    schema_version TEXT  NOT NULL,
    run_id       TEXT    NOT NULL,
    seq          INTEGER NOT NULL,
    ts           TEXT    NOT NULL,
    agent        TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    refs         TEXT,              -- JSON, NULL when the event has no refs
    payload      TEXT    NOT NULL,  -- JSON
    ai_generated INTEGER NOT NULL,
    prev_hash    TEXT    NOT NULL,
    hash         TEXT    NOT NULL,
    PRIMARY KEY (run_id, seq)
)"""


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_hash(event: dict) -> str:
    """sha256(prev_hash + canonical_json(event without its 'hash' field))."""
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256((event["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def first_bad_seq(events: list[dict]) -> int | None:
    """Walk a run's events in order; return the seq of the first broken link, or None."""
    prev = None
    for expected_seq, e in enumerate(events, start=1):
        link_ok = e["prev_hash"] == prev if prev else e["prev_hash"] in (GENESIS_HASH, _LEGACY_GENESIS)
        if e["seq"] != expected_seq or not link_ok or e["hash"] != compute_hash(e):
            return e["seq"]
        prev = e["hash"]
    return None


def _plain_json(obj, what: str) -> dict:
    """Round-trip through JSON so what we hash/return is exactly what we store."""
    try:
        return json.loads(canonical_json(obj))
    except (TypeError, ValueError) as e:
        raise ValidationError(f"{what} is not JSON-serialisable: {e}") from e


class Ledger:
    def __init__(self, path: str | os.PathLike = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
            db.execute(_TABLE)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per call: safe across threads and processes.
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write_tx(self) -> Iterator[sqlite3.Connection]:
        with self._conn() as db:
            db.execute("BEGIN IMMEDIATE")  # take the write lock now; other writers wait
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _insert(db: sqlite3.Connection, e: dict) -> None:
        db.execute(
            f"INSERT INTO events ({', '.join(FIELDS)}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (e["schema_version"], e["seq"], e["ts"], e["run_id"], e["agent"], e["type"],
             canonical_json(e["refs"]) if "refs" in e else None,
             canonical_json(e["payload"]), int(e["ai_generated"]), e["prev_hash"], e["hash"]),
        )

    # ---- write ----

    def append(self, run_id: str, agent: str, type: str, payload: dict,
               refs: dict | None = None, ai_generated: bool = False) -> dict:
        """Validate, then store one event. Returns the full stored event."""
        draft = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "agent": agent, "type": type, "ai_generated": ai_generated,
                 "payload": _plain_json(payload, "payload")}
        if refs:
            draft["refs"] = _plain_json(refs, "refs")
        schemas.validate_envelope(draft, complete=False)
        schemas.validate(type, draft["payload"])

        with self._write_tx() as db:  # seq + prev_hash are computed under the write lock
            last = db.execute(
                "SELECT seq, hash FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1", (run_id,)
            ).fetchone()
            seq, prev_hash = (last[0] + 1, last[1]) if last else (1, GENESIS_HASH)
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            event = {**draft, "seq": seq, "ts": ts, "prev_hash": prev_hash}
            event["hash"] = compute_hash(event)
            self._insert(db, event)
        return {k: event[k] for k in FIELDS if k in event}

    # ---- read ----

    def read(self, run_id: str, after_seq: int = 0) -> list[dict]:
        with self._conn() as db:
            rows = db.execute(
                f"SELECT {', '.join(FIELDS)} FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                (run_id, after_seq),
            ).fetchall()
        events = [dict(zip(FIELDS, row)) for row in rows]
        for e in events:
            e["payload"] = json.loads(e["payload"])
            if e["refs"] is None:
                del e["refs"]
            else:
                e["refs"] = json.loads(e["refs"])
            e["ai_generated"] = bool(e["ai_generated"])
        return events

    def runs(self) -> list[str]:
        with self._conn() as db:
            return [r[0] for r in db.execute("SELECT DISTINCT run_id FROM events ORDER BY run_id")]

    def verify(self, run_id: str) -> tuple[bool, int | None]:
        """Recompute every hash and check the chain. Returns (ok, first_bad_seq)."""
        bad = first_bad_seq(self.read(run_id))
        return bad is None, bad

    def subscribe(self, run_id: str, after_seq: int = 0, poll: float = 0.2,
                  idle_timeout: float | None = None) -> Iterator[dict]:
        """Yield events as they arrive (polling). Runs forever unless idle_timeout
        seconds pass with no new event; the consumer can also just stop iterating."""
        last_event_at = time.monotonic()
        while True:
            for event in self.read(run_id, after_seq):
                after_seq = event["seq"]
                last_event_at = time.monotonic()
                yield event
            if idle_timeout is not None and time.monotonic() - last_event_at >= idle_timeout:
                return
            time.sleep(poll)

    # ---- replay ----

    def export_jsonl(self, run_id: str, path: str | os.PathLike) -> int:
        """Write one event per line. Returns the number of events written."""
        events = self.read(run_id)
        with open(path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(canonical_json(e) + "\n")
        return len(events)

    def import_jsonl(self, path: str | os.PathLike, validate_payloads: bool = True) -> str:
        """Load an exported run, keeping seq/ts/hashes as-is. Returns its run_id.
        Rejects files with a broken chain, invalid events, or a run_id that already exists.
        validate_payloads=False checks only the envelope and the chain; use it to replay
        events from producers whose payloads differ from schemas/ (e.g. bench/arm_a.py)."""
        with open(path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        if not events:
            raise ValidationError(f"{path}: no events")
        for e in events:
            if not isinstance(e, dict):
                raise ValidationError(f"{path}: every line must be a JSON object")
            schemas.validate_envelope(e)  # all required fields, no unknown ones
            if validate_payloads:
                schemas.validate(e["type"], e["payload"])
        run_id = events[0]["run_id"]
        if any(e["run_id"] != run_id for e in events):
            raise ValidationError(f"{path}: more than one run_id in file")
        events.sort(key=lambda e: e["seq"])
        bad = first_bad_seq(events)
        if bad is not None:
            raise ValidationError(f"{path}: hash chain broken at seq {bad}")

        with self._write_tx() as db:
            if db.execute("SELECT 1 FROM events WHERE run_id=? LIMIT 1", (run_id,)).fetchone():
                raise ValidationError(f"run {run_id!r} already exists in {self.path}")
            for e in events:
                self._insert(db, e)
        return run_id
