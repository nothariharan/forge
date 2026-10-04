import json
import os
import shlex
import sys
import textwrap
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arm_a  # noqa: E402
import launch_arm_a as launcher  # noqa: E402
import report  # noqa: E402

ARM_A = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bench", "arm_a.py"))


@pytest.fixture
def spec(tmp_path, monkeypatch):
    (tmp_path / "stub_runner.py").write_text("def run(t, p, s):\n    return {'metrics': {'roc_auc': 0.9}}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return {
        "question": "Does X beat Y?", "task_description": "stub task", "task_id": 1, "data_ver": "stub@1",
        "metric": "roc_auc", "direction": "higher", "practical_threshold": 0.003, "candidate_space": "x, y",
        "wall_clock_minutes": 5, "max_experiments": 2, "usd_cap": "$1", "literature_tools": "none",
        "runner": "stub_runner:run",
    }


def fake_agent(tmp_path, body: str) -> str:
    """A stand-in for `omni run`: a script that drives arm_a.py the way the agent would."""
    script = tmp_path / "fake_agent.py"
    script.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        A = [sys.executable, {ARM_A!r}]
        def call(*args):
            return subprocess.run(A + list(args), capture_output=True, text=True)
    """) + textwrap.dedent(body))
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} {{agent_dir}}"


def test_fill_prompt_fills_every_placeholder_and_refuses_gaps(spec):
    prompt = launcher.fill_prompt(spec)
    assert "Does X beat Y?" in prompt and "OpenML task 1" in prompt and "{" not in prompt.split("Tools")[0]
    assert not launcher.PLACEHOLDER_RE.search(prompt)
    with pytest.raises(SystemExit, match="LITERATURE_TOOLS"):
        launcher.fill_prompt({k: v for k, v in spec.items() if k != "literature_tools"})


def test_dry_run_writes_config_and_prompt_without_starting(spec, tmp_path):
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", dry_run=True)
    config = (ep / "omni_agent" / "config.yaml").read_text()
    assert config.startswith("# Generated") and "spec_version: 1\n" in config and "harness: claude-sdk" in config
    assert "tools:" not in config and "guardrails:" not in config  # arm A has no sub-agents or gates
    assert "Does X beat Y?" not in config and "given in the" in config  # task goes in via -p, not the config
    assert "ASK" not in config  # a headless run cannot answer an approval prompt
    assert (ep / "prompt.md").read_text() == launcher.fill_prompt(spec)
    m = json.loads((ep / "manifest.json").read_text())
    assert m["max_experiments"] == 2 and m["deadline_ts"] and m["seed"] == 1
    assert rec["dry_run"]
    assert rec["command"] == ["omni", "run", str(ep.resolve() / "omni_agent"), "--no-session", "-p", "<prompt.md>"]
    assert [e["type"] for e in arm_a.Episode(str(ep)).events()] == ["RUN_CREATED"]


def test_missing_placeholder_creates_nothing(spec, tmp_path):
    ep = tmp_path / "A" / "seed-1"
    with pytest.raises(SystemExit):
        launcher.launch({k: v for k, v in spec.items() if k != "usd_cap"}, 1, str(ep), dry_run=True)
    assert not ep.exists()


def test_agent_that_answers_completes_the_episode(spec, tmp_path):
    cmd = fake_agent(tmp_path, """
        call("hypothesis", "--hid", "H1", "--claim", "c", "--prediction", "p", "--falsifier", "f", "--prior", "0.5")
        call("predict", "--eid", "E1", "--hid", "H1", "--mean", "0.9", "--sd", "0.01", "--falsifier", "f")
        call("run", "--eid", "E1", "--hid", "H1", "--candidate", "x", "--params", "{}")
        call("answer", "--candidate", "x")
        print("agent done")
    """)
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["returncode"] == 0 and rec["timed_out"] is False and rec["outcome"] == "completed"
    assert "agent done" in (ep / "agent_stdout.log").read_text()
    m = report.episode_metrics(str(ep), {"best": "x", "within_threshold": ["x"]})
    assert m["valid_experiments"] == 1 and m["correct"] is True and m["completed"]


def test_agent_that_quits_without_answer_is_closed_as_aborted(spec, tmp_path):
    cmd = fake_agent(tmp_path, 'call("run", "--eid", "E1", "--hid", "H1", "--candidate", "x", "--params", "{}")\n')
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["outcome"] == "aborted"
    m = report.episode_metrics(str(ep), {"best": "x", "within_threshold": ["x"]})
    assert m["attempts"] == 1 and m["correct"] is None  # stays in the denominator, no answer


def test_agent_past_the_deadline_is_killed_and_closed_as_budget_exhausted(spec, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE_SECONDS", 0)
    spec = {**spec, "wall_clock_minutes": 0.02}  # 1.2 s
    cmd = fake_agent(tmp_path, "time.sleep(30)\n")
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["timed_out"] is True and rec["outcome"] == "budget_exhausted"
    assert json.loads((ep / "manifest.json").read_text())["budget_end_ts"]
    assert json.loads((ep / "launcher.json").read_text())["outcome"] == "budget_exhausted"


def test_budget_caps_are_enforced_by_arm_a(spec, tmp_path):
    ep = tmp_path / "A" / "seed-1"
    launcher.launch(spec, 1, str(ep), run_id="A-1", dry_run=True)
    run = ["--episode", str(ep), "run", "--hid", "H1", "--candidate", "x", "--params", "{}"]
    arm_a.main(run + ["--eid", "E1"])
    arm_a.main(run + ["--eid", "E2"])
    with pytest.raises(SystemExit, match="all 2 experiment runs are used"):
        arm_a.main(run + ["--eid", "E3"])

    manifest = ep / "manifest.json"
    m = json.loads(manifest.read_text())
    m["deadline_ts"] = "2000-01-01T00:00:00Z"
    manifest.write_text(json.dumps(m))
    with pytest.raises(SystemExit, match="answers after the deadline are not accepted"):
        arm_a.main(["--episode", str(ep), "answer", "--candidate", "x"])
    arm_a.main(["--episode", str(ep), "close", "--status", "budget_exhausted"])
    with pytest.raises(SystemExit, match="episode is closed"):
        arm_a.main(run + ["--eid", "E9"])


def test_timeout_stops_processes_the_agent_started(spec, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE_SECONDS", 0)
    spec = {**spec, "wall_clock_minutes": 0.02}
    pidfile = tmp_path / "child.pid"
    cmd = fake_agent(tmp_path, f"""
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open({str(pidfile)!r}, "w").write(str(child.pid))
        time.sleep(60)
    """)
    rec = launcher.launch(spec, 1, str(tmp_path / "ep"), run_id="A-1", agent_cmd=cmd)
    assert rec["timed_out"]
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    assert not _running(pid)


def _running(pid: int) -> bool:
    """True if the process exists and is not a zombie (killed but not yet reaped by init)."""
    if os.name == "nt":
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
    try:
        with open(f"/proc/{pid}/status") as f:
            state = next(line for line in f if line.startswith("State:"))
        return "zombie" not in state
    except FileNotFoundError:
        return False


def test_paths_with_spaces(spec, tmp_path):
    spaced = tmp_path / "dir with space"
    spaced.mkdir()
    cmd = fake_agent(spaced, 'call("answer", "--candidate", "x")\n')
    rec = launcher.launch(spec, 1, str(spaced / "A" / "seed 1"), run_id="A-1", agent_cmd=cmd)
    assert rec["outcome"] == "completed" and rec["agent_dir"].endswith(os.path.join("seed 1", "omni_agent"))


def test_agent_gets_the_filled_prompt_and_a_closed_stdin(spec, tmp_path):
    seen = tmp_path / "seen.json"
    cmd = fake_agent(tmp_path, f"""
        import json
        json.dump({{"argv": sys.argv[1:], "stdin": sys.stdin.read()}}, open({str(seen)!r}, "w"))
        call("answer", "--candidate", "x")
    """) + " --no-session -p {prompt}"
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    got = json.loads(seen.read_text())
    assert got["argv"][1:3] == ["--no-session", "-p"] and got["argv"][3] == (ep / "prompt.md").read_text()
    assert got["stdin"] == ""  # stdin is closed, so a REPL would not wait on it
    assert rec["outcome"] == "completed" and rec["command"][-1] == "<prompt.md>"


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STRAY = os.path.join(REPO_ROOT, "final_report.md")


@pytest.fixture
def clean_repo_root():
    if os.path.exists(STRAY):
        pytest.skip("a final_report.md already exists in the repo root; not touching it")
    yield
    if os.path.exists(STRAY):
        os.remove(STRAY)


def test_report_written_in_repo_root_is_moved_into_the_episode(spec, tmp_path, clean_repo_root):
    # The agent runs with cwd = repo root, writes final_report.md there and passes the relative path.
    cmd = fake_agent(tmp_path, """
        open("final_report.md", "w").write("# answer x")
        r = call("answer", "--candidate", "x", "--report", "final_report.md")
        print(r.stdout, r.stderr)
    """)
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["outcome"] == "completed"
    assert (ep / "final_report.md").read_text() == "# answer x"
    assert not os.path.exists(STRAY)  # nothing left behind for the next episode to overwrite


def test_stray_report_without_answer_flag_is_collected(spec, tmp_path, clean_repo_root):
    cmd = fake_agent(tmp_path, """
        open("final_report.md", "w").write("# stray")
        call("answer", "--candidate", "x")
    """)
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["stray_report_moved"] == "final_report.md" and not os.path.exists(STRAY)
    assert (ep / "final_report.md").read_text() == "# stray"


def test_missing_report_file_is_refused_before_answering(spec, tmp_path):
    ep = tmp_path / "A" / "seed-1"
    launcher.launch(spec, 1, str(ep), run_id="A-1", dry_run=True)
    with pytest.raises(SystemExit, match="report file not found"):
        arm_a.main(["--episode", str(ep), "answer", "--candidate", "x", "--report", "nope.md"])
    assert not (ep / "answer.json").exists()


def test_agent_dying_with_exit_code_0_records_the_reason(spec, tmp_path):
    cmd = fake_agent(tmp_path, """
        print("Error: authentication failed (401): invalid x-api-key", file=sys.stderr)
        sys.exit(0)
    """)
    ep = tmp_path / "A" / "seed-1"
    rec = launcher.launch(spec, 1, str(ep), run_id="A-1", agent_cmd=cmd)
    assert rec["outcome"] == "aborted" and rec["returncode"] == 0
    assert "exited with code 0 but submitted no answer" in rec["failure_reason"]
    assert "authentication failed" in rec["failure_reason"]
    saved = json.loads((ep / "launcher.json").read_text())
    assert "authentication failed" in saved["failure_reason"]
    closed = [e for e in arm_a.Episode(str(ep)).events() if e["type"] == "RUN_COMPLETED"][0]
    assert "authentication failed" in closed["payload"]["summary"]


def test_timeout_reason(spec, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE_SECONDS", 0)
    rec = launcher.launch({**spec, "wall_clock_minutes": 0.01}, 1, str(tmp_path / "ep"), run_id="A-1",
                          agent_cmd=fake_agent(tmp_path, "time.sleep(30)\n"))
    assert rec["failure_reason"].startswith("agent was stopped at the wall-clock budget")
