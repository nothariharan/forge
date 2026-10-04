import json

from core.ledger import Ledger
from tools import forge_emit

HYP = {"hid": "H1", "claim": "c", "prediction": "p", "falsifier": "f", "prior": 0.6}


def _run(db, type_, payload, agent="hypothesizer"):
    return forge_emit.main(["--db", str(db), "--run-id", "r", "--agent", agent,
                            "--type", type_, "--payload", payload, "--ai-generated"])


def test_valid_handoff_is_appended(tmp_path, capsys):
    db = tmp_path / "l.db"
    assert _run(db, "HYPOTHESIS_PROPOSED", json.dumps(HYP)) == 0
    assert "FORGE_EMIT_OK" in capsys.readouterr().out
    [ev] = Ledger(db).read("r")
    assert ev["type"] == "HYPOTHESIS_PROPOSED" and ev["ai_generated"] is True


def test_schema_failure_is_rejected_and_recorded(tmp_path, capsys):
    db = tmp_path / "l.db"
    bad = {"id": "H1", "claim": "c"}  # old hypothesizer shape: no hid/prediction/falsifier/prior
    assert _run(db, "HYPOTHESIS_PROPOSED", json.dumps(bad)) == 2
    assert "FORGE_EMIT_REJECTED" in capsys.readouterr().out
    events = Ledger(db).read("r")
    assert [e["type"] for e in events] == ["ERROR"]
    assert events[0]["payload"]["rejected_type"] == "HYPOTHESIS_PROPOSED"
    assert '"id": "H1"' in events[0]["payload"]["raw"]


def test_bad_json_is_rejected(tmp_path):
    db = tmp_path / "l.db"
    assert _run(db, "HYPOTHESIS_PROPOSED", "{not json") == 2
    assert Ledger(db).read("r")[0]["payload"]["message"].startswith("handoff rejected: invalid JSON")


def test_unknown_type_is_rejected(tmp_path):
    db = tmp_path / "l.db"
    assert _run(db, "NOT_A_TYPE", json.dumps(HYP)) == 2
    assert [e["type"] for e in Ledger(db).read("r")] == ["ERROR"]


def test_chain_verifies_after_mixed_handoffs(tmp_path):
    db = tmp_path / "l.db"
    _run(db, "HYPOTHESIS_PROPOSED", json.dumps(HYP))
    _run(db, "HYPOTHESIS_PROPOSED", "{}")
    assert Ledger(db).verify("r") == (True, None)


def test_second_run_created_is_skipped(tmp_path, capsys):
    db = tmp_path / "l.db"
    Ledger(db).append("r", "system", "RUN_CREATED", {"question": "q", "mode": "benchmark"})
    assert _run(db, "RUN_CREATED", json.dumps({"question": "q", "mode": "live"}), agent="director") == 0
    assert "skipped" in capsys.readouterr().out
    assert [e["type"] for e in Ledger(db).read("r")] == ["RUN_CREATED"]
