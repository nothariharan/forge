import json
import sqlite3
import threading
from collections import Counter

import pytest

from cli import verify as verify_cli
from core import schemas
from core.fake_events import emit_fake_run
from core.ledger import GENESIS_HASH, Ledger, ValidationError, compute_hash

HYP = {"hid": "H1", "claim": "c", "prediction": "p", "falsifier": "f", "prior": 0.5}
RUN = {"eid": "E1", "hid": "H1", "code_hash": "a", "data_ver": "v", "seed": 0}
SPEC = {
    "candidates": [
        {"eid": "E1", "hid": "H1", "design": "d1", "est_cost": 1.0, "eig": 0.4},
        {"eid": "E2", "hid": "H2", "design": "d2", "est_cost": 2.0, "eig": 0.5},
    ],
    "chosen": "E1",
    "budget_left": 10,
}


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.db")


def add(ledger, run_id="r1", n=1):
    return [ledger.append(run_id, "hypothesizer", "HYPOTHESIS_PROPOSED", {**HYP, "hid": f"H{i}"}) for i in range(n)]


def test_append_and_read(ledger):
    event = ledger.append("r1", "hypothesizer", "HYPOTHESIS_PROPOSED", HYP, refs={"hid": "H1"}, ai_generated=True)
    assert event["seq"] == 1
    assert event["schema_version"] == "1.0"
    assert event["prev_hash"] == GENESIS_HASH
    assert event["hash"] == compute_hash(event)
    assert event["payload"] == HYP and event["refs"] == {"hid": "H1"} and event["ai_generated"] is True
    assert event["ts"].endswith("Z")
    assert ledger.read("r1") == [event]
    assert "refs" not in add(ledger, "r2")[0]  # refs is left out when empty
    assert ledger.runs() == ["r1", "r2"]


def test_seq_increments_per_run(ledger):
    add(ledger, "r1", 3)
    add(ledger, "r2", 2)
    assert [e["seq"] for e in ledger.read("r1")] == [1, 2, 3]
    assert [e["seq"] for e in ledger.read("r2")] == [1, 2]
    assert [e["seq"] for e in ledger.read("r1", after_seq=1)] == [2, 3]
    assert ledger.runs() == ["r1", "r2"]


def test_hash_chain_verifies(ledger):
    events = add(ledger, n=5)
    for prev, cur in zip(events, events[1:]):
        assert cur["prev_hash"] == prev["hash"]
    assert ledger.verify("r1") == (True, None)


def test_tampered_payload_fails_at_right_seq(ledger):
    add(ledger, n=5)
    db = sqlite3.connect(ledger.path)
    db.execute("UPDATE events SET payload=? WHERE run_id='r1' AND seq=3", (json.dumps({**HYP, "prior": 0.99}),))
    db.commit()
    db.close()
    assert ledger.verify("r1") == (False, 3)


@pytest.mark.parametrize("kwargs", [
    dict(type="HYPOTHESIS_PROPOSED", payload={**HYP, "prior": 1.5}),            # out of range
    dict(type="HYPOTHESIS_PROPOSED", payload={"hid": "H1"}),                     # missing fields
    dict(type="PREDICTION_COMMITTED", payload={"hid": "H1", "metric": "m", "mean": 0, "sd": 0}),  # sd must be > 0
    dict(type="RUN_FINISHED", payload={**RUN, "status": "ok"}),                   # no metrics
    dict(type="RUN_FINISHED", payload={**RUN, "metrics": {"auc": 0.8}}),         # no status
    dict(type="RUN_STARTED", payload={k: v for k, v in RUN.items() if k != "hid"}),  # no hid
    dict(type="NOT_A_TYPE", payload={}),
    dict(type="HYPOTHESIS_PROPOSED", payload=HYP, agent=""),                     # empty agent
    dict(type="HYPOTHESIS_PROPOSED", payload={**HYP, "extra": {1, 2}}),          # not JSON
])
def test_invalid_event_rejected_and_nothing_written(ledger, kwargs):
    add(ledger, n=1)
    args = {"run_id": "r1", "agent": "hypothesizer", **kwargs}
    with pytest.raises(ValidationError):
        ledger.append(**args)
    assert len(ledger.read("r1")) == 1
    assert ledger.verify("r1") == (True, None)


def test_empty_evidence_is_an_honest_no_evidence_event(ledger):
    assert ledger.append("r1", "librarian", "EVIDENCE_ADDED", {"claims": []})["seq"] == 1
    with pytest.raises(ValidationError):  # a claim, when present, still needs text, ref and quote
        ledger.append("r1", "librarian", "EVIDENCE_ADDED", {"claims": [{"text": "t"}]})


def test_spec_chosen_must_be_a_candidate(ledger):
    assert ledger.append("r1", "planner", "EXPERIMENT_SELECTED", SPEC)["seq"] == 1
    with pytest.raises(ValidationError, match="chosen"):
        ledger.append("r1", "planner", "EXPERIMENT_SELECTED", {**SPEC, "chosen": "E9"})
    assert len(ledger.read("r1")) == 1


def test_export_import_round_trip(ledger, tmp_path):
    emit_fake_run(ledger, "r1")
    out = tmp_path / "r1.jsonl"
    assert ledger.export_jsonl("r1", out) == len(ledger.read("r1"))

    other = Ledger(tmp_path / "other.db")
    assert other.import_jsonl(out) == "r1"
    assert other.read("r1") == ledger.read("r1")
    assert [e["hash"] for e in other.read("r1")] == [e["hash"] for e in ledger.read("r1")]
    assert other.verify("r1") == (True, None)

    with pytest.raises(ValidationError, match="already exists"):
        other.import_jsonl(out)


def test_import_rejects_tampered_file(ledger, tmp_path):
    add(ledger, n=3)
    out = tmp_path / "r1.jsonl"
    ledger.export_jsonl("r1", out)
    lines = out.read_text().splitlines()
    second = json.loads(lines[1])
    second["payload"]["prior"] = 0.99
    lines[1] = json.dumps(second)
    out.write_text("\n".join(lines) + "\n")

    other = Ledger(tmp_path / "other.db")
    with pytest.raises(ValidationError, match="seq 2"):
        other.import_jsonl(out)
    assert other.runs() == []


def test_concurrent_appends_from_4_threads(ledger):
    per_thread, errors = 25, []

    def worker(t):
        try:
            mine = Ledger(ledger.path)  # separate Ledger per thread, same file
            for i in range(per_thread):
                mine.append("r1", "hypothesizer", "HYPOTHESIS_PROPOSED", {**HYP, "hid": f"H{t}-{i}"})
        except Exception as e:  # surfaced below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    events = ledger.read("r1")
    assert [e["seq"] for e in events] == list(range(1, 4 * per_thread + 1))  # no gaps, no duplicates
    assert len({e["payload"]["hid"] for e in events}) == 4 * per_thread
    assert ledger.verify("r1") == (True, None)


def test_subscribe_yields_old_then_new_events(ledger):
    add(ledger, n=2)
    writer = threading.Timer(0.1, lambda: add(Ledger(ledger.path), n=2))
    writer.start()
    seqs = [e["seq"] for e in ledger.subscribe("r1", after_seq=1, poll=0.02, idle_timeout=0.5)]
    writer.join()
    assert seqs == [2, 3, 4]


def test_fake_events_run_verifies(ledger):
    events = emit_fake_run(ledger, "demo")
    assert ledger.verify("demo") == (True, None)
    counts = Counter(e["type"] for e in events)
    assert counts == {
        "RUN_CREATED": 1, "RUN_COMPLETED": 1,
        "EVIDENCE_ADDED": 3, "HYPOTHESIS_PROPOSED": 4, "NOVELTY_VERDICT": 4, "PREDICTION_COMMITTED": 3,
        "EXPERIMENT_SELECTED": 2, "RUN_STARTED": 2, "RUN_FINISHED": 2, "FINDING": 2, "CONSENSUS": 2,
        "SURPRISE": 1, "REPLAN": 1, "POLICY_DENIED": 1, "GATE_OPENED": 1, "GATE_RESOLVED": 1,
    }
    assert set(schemas.EVENT_TYPES) - set(counts) == {"ERROR"}  # every other event type appears
    assert events[0]["type"] == "RUN_CREATED" and events[-1]["type"] == "RUN_COMPLETED"
    assert [e["payload"]["label"] for e in events if e["type"] == "NOVELTY_VERDICT"].count("KNOWN") == 1
    assert events[-2]["type"] == "GATE_RESOLVED" and events[-2]["payload"]["status"] == "approved"


def test_verify_cli_exit_codes(ledger, capsys):
    emit_fake_run(ledger, "demo")
    db = ["--db", str(ledger.path)]
    assert verify_cli.main(["demo", *db]) == 0
    assert "chain OK, 31 events" in capsys.readouterr().out

    conn = sqlite3.connect(ledger.path)
    conn.execute("UPDATE events SET agent='system' WHERE run_id='demo' AND seq=7")
    conn.commit()
    conn.close()
    assert verify_cli.main(["demo", *db]) == 1
    assert "BROKEN at seq 7" in capsys.readouterr().out
    assert verify_cli.main(["missing", *db]) == 1


def test_verify_cli_checks_an_exported_jsonl(ledger, tmp_path, capsys):
    emit_fake_run(ledger, "demo")
    out = tmp_path / "events.jsonl"
    ledger.export_jsonl("demo", out)
    assert verify_cli.main(["demo", "--jsonl", str(out)]) == 0
    assert "chain OK, 31 events" in capsys.readouterr().out
    lines = out.read_text().splitlines()
    tampered = json.loads(lines[4])
    tampered["agent"] = "system"
    lines[4] = json.dumps(tampered)
    out.write_text("\n".join(lines) + "\n")
    assert verify_cli.main(["demo", "--jsonl", str(out)]) == 1
    assert "BROKEN at seq 5" in capsys.readouterr().out
    assert verify_cli.main(["missing", "--jsonl", str(out)]) == 1


def test_python_event_types_match_shared_envelope_schema():
    envelope = json.loads((schemas.SCHEMA_DIR / "event.schema.json").read_text())
    assert tuple(envelope["properties"]["type"]["enum"]) == schemas.EVENT_TYPES


def test_stored_events_satisfy_shared_envelope_schema(ledger):
    for event in emit_fake_run(ledger, "demo"):
        schemas.validate_envelope(event)  # all ten required fields, no extras


def test_benchmark_payload_keys_present(ledger):
    """Keys bench/report.py reads (docs/coordination/BENCHMARK.md)."""
    events = emit_fake_run(ledger, "demo")
    by_type = lambda t: [e["payload"] for e in events if e["type"] == t]
    assert all("hid" in p for p in by_type("HYPOTHESIS_PROPOSED"))
    assert all({"eid", "hid"} <= set(p) for p in by_type("RUN_STARTED"))
    assert all({"eid", "status", "metrics"} <= set(p) for p in by_type("RUN_FINISHED"))
    assert all("trigger_eid" in p for p in by_type("REPLAN"))
    # every run is preregistered: a PREDICTION_COMMITTED with its eid comes first
    committed = set()
    for e in events:
        if e["type"] == "PREDICTION_COMMITTED":
            committed.add(e["payload"]["eid"])
        if e["type"] == "RUN_STARTED":
            assert e["payload"]["eid"] in committed


def test_extra_event_types_and_uncertain_label(ledger):
    ledger.append("r1", "system", "RUN_CREATED", {"question": "q"})
    ledger.append("r1", "referee", "NOVELTY_VERDICT", {"hid": "H1", "label": "UNCERTAIN", "prior_art": []})
    ledger.append("r1", "experimenter", "ERROR", {"message": "sandbox timeout"})
    ledger.append("r1", "baseline", "RUN_COMPLETED", {"status": "aborted"})  # any agent name is allowed
    assert ledger.verify("r1") == (True, None)


def test_import_baseline_arm_events(ledger, tmp_path):
    """bench/arm_a.py writes its own events.jsonl: no refs, looser payloads, same hash rule."""
    events, prev = [], GENESIS_HASH
    for seq, (type, payload) in enumerate([("RUN_CREATED", {"question": "q", "arm": "A"}),
                                           ("HYPOTHESIS_PROPOSED", {"hid": "H1", "claim": "c", "label": "AI-generated"}),
                                           ("RUN_COMPLETED", {"candidate": "rf"})], start=1):
        e = {"schema_version": "1.0", "seq": seq, "ts": "2026-10-04T00:00:00.000000Z", "run_id": "A-seed1",
             "agent": "baseline", "type": type, "payload": payload, "ai_generated": True, "prev_hash": prev}
        e["hash"] = prev = compute_hash(e)
        events.append(e)
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))

    with pytest.raises(ValidationError):  # payloads do not match schemas/
        ledger.import_jsonl(path)
    assert ledger.import_jsonl(path, validate_payloads=False) == "A-seed1"
    assert ledger.read("A-seed1") == events
    assert ledger.verify("A-seed1") == (True, None)
