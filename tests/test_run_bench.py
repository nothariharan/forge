import json
import os
import shlex
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import launch_arm_a  # noqa: E402
import launch_arm_b  # noqa: E402
import report  # noqa: E402
import run_bench  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARM_A = os.path.join(REPO, "bench", "arm_a.py")


@pytest.fixture
def spec(tmp_path, monkeypatch):
    (tmp_path / "bench_e2e_runner.py").write_text(
        "def run(t, p, s):\n    return {'metrics': {'roc_auc': {'x': 0.80, 'y': 0.90}.get(p.get('c'), 0.5)}}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + REPO + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return {
        "question": "Does y beat x?", "task_description": "stub task", "task_id": 1, "data_ver": "stub@1",
        "metric": "roc_auc", "direction": "higher", "practical_threshold": 0.003, "candidate_space": "x, y",
        "wall_clock_minutes": 5, "max_experiments": 3, "usd_cap": "$1", "literature_tools": "none", "answer_options": "x, y",
        "runner": "bench_e2e_runner:run",
    }


def script(tmp_path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(f"""
        import json, os, subprocess, sys, time
        sys.path.insert(0, {REPO!r})
        A = [sys.executable, {ARM_A!r}]
        def call(*args):
            return subprocess.run(A + list(args), capture_output=True, text=True)
    """) + textwrap.dedent(body))
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(path))}"


FAKE_A = """
    call("predict", "--eid", "E1", "--hid", "H1", "--mean", "0.8", "--sd", "0.02", "--falsifier", "f")
    call("run", "--eid", "E1", "--hid", "H1", "--candidate", "x", "--params", '{"c": "x"}')
    call("answer", "--candidate", "x")
"""

# Like FORGE's director: events go to the ledger in $FORGE_LEDGER_DB, run id comes from the task message,
# and experiments are logged with RUN_FINISHED only (no RUN_STARTED).
FAKE_B = """
    from core.ledger import Ledger
    msg = sys.argv[sys.argv.index("-p") + 1]
    run_id = msg.split("Run id: ", 1)[1].split()[0]
    L = Ledger(os.environ["FORGE_LEDGER_DB"])
    for eid, c in (("E1", "x"), ("E2", "y")):
        L.append(run_id, "planner", "PREDICTION_COMMITTED", {"eid": eid, "hid": "H1", "metric": "roc_auc", "mean": 0.85, "sd": 0.03}, ai_generated=True)
        L.append(run_id, "experimenter", "RUN_FINISHED", {"eid": eid, "hid": "H1", "code_hash": "sha256:x", "data_ver": "stub@1",
                 "seed": 1, "status": "ok", "metrics": {"roc_auc": 0.8 if c == "x" else 0.9}, "candidate": c})
    L.append(run_id, "system", "RUN_COMPLETED", {"status": "completed", "summary": "y wins", "candidate": "y"}, ai_generated=True)
"""


def test_task_message_shares_the_arm_a_sections_verbatim(spec):
    filled = launch_arm_a.fill_prompt(spec)
    msg = launch_arm_b.task_message(spec, "B-1")
    assert msg.startswith("Run id: B-1\n")
    for heading in launch_arm_b.SHARED_SECTIONS:
        assert launch_arm_b._section(filled, heading) in msg
    assert "### Tools" not in msg and "bench/arm_a.py" not in msg  # arm A's tool instructions are not given to FORGE
    assert '"candidate"' in msg


def test_arm_b_episode_is_scored_like_arm_a(spec, tmp_path):
    ep = tmp_path / "B" / "seed-1"
    rec = launch_arm_b.launch(spec, 1, str(ep), run_id="B-1", agent_cmd=script(tmp_path, "fb.py", FAKE_B) + " -p {prompt}")
    assert rec["outcome"] == "completed"
    assert json.loads((ep / "answer.json").read_text())["candidate"] == "y"
    events = [json.loads(l) for l in open(ep / "events.jsonl")]
    assert events[0]["type"] == "RUN_CREATED" and events[0]["agent"] == "system"
    m = report.episode_metrics(str(ep), {"best": "y", "within_threshold": ["y"]})
    assert m["attempts"] == 2 and m["valid_experiments"] == 2 and m["prereg_violations"] == 0
    assert m["experiments_to_top"] == 2 and m["correct"] is True


def test_arm_b_without_completion_is_closed(spec, tmp_path):
    ep = tmp_path / "B" / "seed-1"
    rec = launch_arm_b.launch(spec, 1, str(ep), run_id="B-1", agent_cmd=script(tmp_path, "quit.py", "pass\n"))
    assert rec["outcome"] == "aborted" and not (ep / "answer.json").exists()
    assert json.loads((ep / "manifest.json").read_text())["budget_end_ts"]


def test_run_order_alternates():
    assert run_bench.run_order([1, 2, 3], ["A", "B"]) == [(1, "A"), (1, "B"), (2, "B"), (2, "A"), (3, "A"), (3, "B")]


def test_end_to_end_bench_writes_a_report(spec, tmp_path):
    oracle_spec = tmp_path / "oracle_spec.json"
    oracle_spec.write_text(json.dumps({
        "task_id": 1, "metric": "roc_auc", "direction": "maximize", "practical_threshold": 0.003, "seeds": [1],
        "runner": "bench_e2e_runner:run", "candidates": [{"id": "x", "params": {"c": "x"}}, {"id": "y", "params": {"c": "y"}}],
    }))
    out = tmp_path / "results"
    res = run_bench.run_bench(spec, "t1", [1, 2, 3], out_root=str(out), oracle_spec=str(oracle_spec),
                              arm_a_cmd=script(tmp_path, "fa.py", FAKE_A),
                              arm_b_cmd=script(tmp_path, "fb.py", FAKE_B) + " -p {prompt}")
    bench = out / "t1"
    assert [(l["arm"], l["seed"], l["outcome"]) for l in res["launches"]] == [
        ("A", 1, "completed"), ("B", 1, "completed"), ("B", 2, "completed"),
        ("A", 2, "completed"), ("A", 3, "completed"), ("B", 3, "completed")]
    cmp = json.loads((bench / "report.json").read_text())["comparison"]
    assert cmp["paired_seeds"] == [1, 2, 3]
    assert cmp["pooled"]["A"]["correct"][:2] == [0, 3] and cmp["pooled"]["B"]["correct"][:2] == [3, 3]
    assert cmp["throughput_multiplier"]["estimate"] is not None
    assert "Throughput multiplier" in (bench / "report.md").read_text()

    # Resuming skips finished episodes; nothing is launched twice.
    again = run_bench.run_bench(spec, "t1", [1, 2, 3], out_root=str(out), arm_a_cmd="false", arm_b_cmd="false")
    assert len(again["launches"]) == 6


def test_a_failed_launch_is_recorded(spec, tmp_path):
    bad = {k: v for k, v in spec.items() if k != "usd_cap"}  # a missing placeholder makes the launch fail
    res = run_bench.run_bench(bad, "t2", [1], arms=["A"], out_root=str(tmp_path / "r"), dry_run=True)
    assert res["launches"][0]["outcome"] == "launch_failed" and "USD_CAP" in res["launches"][0]["error"]
    saved = json.loads((tmp_path / "r" / "t2" / "bench_manifest.json").read_text())
    assert saved["launches"][0]["outcome"] == "launch_failed"


def test_dry_run_initialises_both_arms(spec, tmp_path):
    res = run_bench.run_bench(spec, "t3", [1], out_root=str(tmp_path / "r"), dry_run=True)
    assert [l["outcome"] for l in res["launches"]] == ["dry_run", "dry_run"] and "report" not in res
    assert (tmp_path / "r" / "t3" / "B" / "seed-1" / "prompt.md").read_text().startswith("Run id: t3-B-1")
