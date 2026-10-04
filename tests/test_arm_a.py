import json
import os
import sys

import pytest

BENCH = os.path.join(os.path.dirname(__file__), "..", "bench")
sys.path.insert(0, BENCH)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arm_a  # noqa: E402
import report  # noqa: E402
from core import schemas as core_schemas  # noqa: E402
from core.ledger import Ledger, first_bad_seq  # noqa: E402

SCHEMA = json.load(open(os.path.join(os.path.dirname(__file__), "..", "schemas", "event.schema.json")))


@pytest.fixture
def episode(tmp_path, monkeypatch):
    (tmp_path / "fake_run_mod.py").write_text(
        "def run(task_id, params, seed):\n"
        "    if params.get('model') == 'boom':\n"
        "        raise RuntimeError('crashed')\n"
        "    return {'metrics': {'auc': {'lr': 0.80, 'rf': 0.86}[params['model']]}}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    ep = tmp_path / "bench" / "A" / "seed-1"
    monkeypatch.setenv("FORGE_EPISODE_DIR", str(ep))
    arm_a.main(["init", "--seed", "1", "--question", "Q?", "--metric", "auc",
                "--runner", "fake_run_mod:run", "--task-id", "31", "--data-ver", "openml:31@1", "--run-id", "A-1"])
    return ep


def _events(ep):
    return [json.loads(l) for l in open(ep / "events.jsonl")]


def test_full_episode_is_schema_shaped_hash_chained_and_scorable(episode, tmp_path):
    arm_a.main(["hypothesis", "--hid", "H1", "--claim", "rf beats lr", "--prediction", "rf auc > lr auc",
                "--falsifier", "rf <= lr", "--prior", "0.6"])
    arm_a.main(["predict", "--eid", "E1", "--hid", "H1", "--mean", "0.82", "--sd", "0.01", "--falsifier", "auc < 0.8"])
    arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    arm_a.main(["decide", "--after", "E1", "--decision", "try rf next", "--changed", "--reopen", "H1"])
    arm_a.main(["decide", "--after", "E1", "--decision", "keep going"])
    arm_a.main(["run", "--eid", "E2", "--hid", "H1", "--candidate", "rf", "--params", '{"model": "rf"}'])  # no prediction
    arm_a.main(["run", "--eid", "E3", "--hid", "H1", "--candidate", "boom", "--params", '{"model": "boom"}'])
    report_md = tmp_path / "draft.md"
    report_md.write_text("# answer: rf")
    arm_a.main(["answer", "--candidate", "rf", "--report", str(report_md)])

    events = _events(episode)
    allowed = set(SCHEMA["properties"]["type"]["enum"])
    for i, e in enumerate(events, start=1):
        assert set(SCHEMA["required"]) <= set(e) and set(e) <= set(SCHEMA["properties"])
        assert e["type"] in allowed and e["seq"] == i
    assert events[0]["prev_hash"] == "GENESIS" and first_bad_seq(events) is None
    assert Ledger(episode / "ledger.db").verify("A-1") == (True, None)
    assert Ledger(episode / "ledger.db").read("A-1") == events  # events.jsonl is the ledger export
    assert [e["type"] for e in events if e["ai_generated"]] == [
        "HYPOTHESIS_PROPOSED", "PREDICTION_COMMITTED", "REPLAN", "RUN_COMPLETED"]

    records = [json.loads(l) for l in open(episode / "run_records.jsonl")]
    assert [r["status"] for r in records] == ["ok", "ok", "error"] and "crashed" in records[2]["error"]
    assert (episode / "final_report.md").read_text() == "# answer: rf"
    decisions = [json.loads(l) for l in open(episode / "decisions.jsonl")]
    assert decisions == [{**decisions[0], "after": "E1", "decision": "keep going", "plan_changed": False}]
    started = next(e for e in events if e["type"] == "RUN_STARTED")["payload"]
    assert started["data_ver"] == "openml:31@1" and started["seed"] == 1 and started["code_hash"].startswith("sha256:")

    m = report.episode_metrics(str(episode), {"best": "rf", "within_threshold": ["rf"]})
    assert m["attempts"] == 3 and m["valid_experiments"] == 1
    assert m["prereg_violations"] == 2  # E2 and E3 ran without a committed prediction
    assert m["replans"] == 1 and m["completed"] and m["correct"] is True
    assert m["hypotheses_tested"] == 1


def test_guards(episode):
    with pytest.raises(SystemExit, match="already started"):
        arm_a.main(["init", "--seed", "1", "--question", "Q", "--metric", "auc", "--runner", "x:y", "--task-id", "1",
                    "--data-ver", "v1"])
    with pytest.raises(SystemExit, match="sd must be greater than 0"):
        arm_a.main(["predict", "--eid", "E9", "--hid", "H1", "--mean", "0.8", "--sd", "0", "--falsifier", "x"])
    with pytest.raises(SystemExit, match="prior must be between"):
        arm_a.main(["hypothesis", "--hid", "H9", "--claim", "c", "--prediction", "p", "--falsifier", "f", "--prior", "1.5"])
    arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    with pytest.raises(SystemExit, match="already used"):
        arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    arm_a.main(["answer", "--candidate", "lr"])
    with pytest.raises(SystemExit, match="already submitted"):
        arm_a.main(["answer", "--candidate", "rf"])


def test_requires_episode_dir(monkeypatch):
    monkeypatch.delenv("FORGE_EPISODE_DIR", raising=False)
    with pytest.raises(SystemExit, match="FORGE_EPISODE_DIR"):
        arm_a.main(["hypothesis", "--hid", "H1", "--claim", "x", "--prediction", "p", "--falsifier", "f", "--prior", "0.5"])


def test_payloads_pass_shared_payload_schemas(episode, tmp_path):
    arm_a.main(["hypothesis", "--hid", "H1", "--claim", "c", "--prediction", "p", "--falsifier", "f", "--prior", "0.5"])
    arm_a.main(["predict", "--eid", "E1", "--hid", "H1", "--mean", "0.8", "--sd", "0.01", "--falsifier", "f"])
    arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    arm_a.main(["run", "--eid", "E2", "--hid", "H1", "--candidate", "boom", "--params", '{"model": "boom"}'])
    arm_a.main(["decide", "--after", "E1", "--decision", "switch", "--changed", "--reopen", "H1"])
    arm_a.main(["answer", "--candidate", "lr"])
    for e in _events(episode):
        core_schemas.validate(e["type"], e["payload"])
        core_schemas.validate_envelope(e)


def test_refs_link_experiments_to_hypotheses(episode):
    arm_a.main(["hypothesis", "--hid", "H1", "--claim", "c", "--prediction", "p", "--falsifier", "f", "--prior", "0.5"])
    arm_a.main(["predict", "--eid", "E1", "--hid", "H1", "--mean", "0.8", "--sd", "0.01", "--falsifier", "f"])
    arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    arm_a.main(["decide", "--after", "E1", "--decision", "switch", "--changed"])
    refs = {e["type"]: e.get("refs") for e in _events(episode)}
    assert refs["RUN_CREATED"] is None
    assert refs["HYPOTHESIS_PROPOSED"] == {"hid": "H1"}
    assert refs["PREDICTION_COMMITTED"] == refs["RUN_STARTED"] == refs["RUN_FINISHED"] == {"hid": "H1", "eid": "E1"}
    assert refs["REPLAN"] == {"eid": "E1"}


def test_invalid_payload_is_rejected_and_nothing_is_written(episode):
    before = _events(episode)
    with pytest.raises(SystemExit, match="rejected by the ledger"):
        arm_a.main(["hypothesis", "--hid", "H1", "--claim", "", "--prediction", "p", "--falsifier", "f", "--prior", "0.5"])
    assert _events(episode) == before
    assert Ledger(episode / "ledger.db").read("A-1") == before


def test_shared_ledger_holds_several_episodes(tmp_path, monkeypatch):
    (tmp_path / "stub_mod.py").write_text("def run(t, p, s):\n    return {'metrics': {'auc': 0.7}}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    shared = tmp_path / "shared.db"
    for seed in (1, 2):
        ep = tmp_path / "A" / f"seed-{seed}"
        arm_a.main(["--episode", str(ep), "init", "--seed", str(seed), "--question", "Q", "--metric", "auc",
                    "--runner", "stub_mod:run", "--task-id", "1", "--data-ver", "v1", "--run-id", f"A-{seed}",
                    "--ledger", str(shared)])
        arm_a.main(["--episode", str(ep), "run", "--eid", "E1", "--hid", "H1", "--candidate", "c", "--params", "{}"])
        assert not (ep / "ledger.db").exists()
    ledger = Ledger(shared)
    assert ledger.runs() == ["A-1", "A-2"]
    assert all(ledger.verify(r) == (True, None) for r in ledger.runs())
    with pytest.raises(SystemExit, match="already exists in the ledger"):
        arm_a.main(["--episode", str(tmp_path / "other"), "init", "--seed", "1", "--question", "Q", "--metric", "auc",
                    "--runner", "stub_mod:run", "--task-id", "1", "--data-ver", "v1", "--run-id", "A-1",
                    "--ledger", str(shared)])
