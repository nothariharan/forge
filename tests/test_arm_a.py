import hashlib
import json
import os
import sys

import pytest

BENCH = os.path.join(os.path.dirname(__file__), "..", "bench")
sys.path.insert(0, BENCH)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arm_a  # noqa: E402
import report  # noqa: E402

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
    prev = "GENESIS"
    for i, e in enumerate(events, start=1):
        assert set(SCHEMA["required"]) <= set(e) and set(e) <= set(SCHEMA["properties"])
        assert e["type"] in allowed and e["seq"] == i and e["prev_hash"] == prev
        body = {k: v for k, v in e.items() if k != "hash"}
        assert e["hash"] == hashlib.sha256((prev + arm_a._canonical(body)).encode()).hexdigest()
        prev = e["hash"]
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
    """Runs once core/schemas.py (PR #4) is on the branch; skipped before that."""
    core_schemas = pytest.importorskip("core.schemas")
    arm_a.main(["hypothesis", "--hid", "H1", "--claim", "c", "--prediction", "p", "--falsifier", "f", "--prior", "0.5"])
    arm_a.main(["predict", "--eid", "E1", "--hid", "H1", "--mean", "0.8", "--sd", "0.01", "--falsifier", "f"])
    arm_a.main(["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr", "--params", '{"model": "lr"}'])
    arm_a.main(["run", "--eid", "E2", "--hid", "H1", "--candidate", "boom", "--params", '{"model": "boom"}'])
    arm_a.main(["decide", "--after", "E1", "--decision", "switch", "--changed", "--reopen", "H1"])
    arm_a.main(["answer", "--candidate", "lr"])
    for e in _events(episode):
        core_schemas.validate(e["type"], e["payload"])
        core_schemas.validate_envelope(e)
