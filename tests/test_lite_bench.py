import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))

import aggregate_lite  # noqa: E402
import run_lite_seed  # noqa: E402
from test_run_bench import FAKE_A, FAKE_B, script, spec  # noqa: E402,F401

ORACLE = {"best": "y", "within_threshold": ["y"]}
SETUP = {"omni_version": "0.16.0", "model": "model-x", "snapshot_sha256": "f" * 64, "code_commit": "c" * 40,
         "omni_version_found": "0.16.0", "head_commit": "d" * 40}
LOCK = {k: SETUP[k] for k in run_lite_seed.LOCK_KEYS} | {"code_paths": ["bench"]}
SECRETS = ["sk-ant-api03-SECRETSECRETSECRET", "ghp_SECRETSECRETSECRET1234", "hunter2-not-a-path"]


@pytest.fixture
def lite(spec, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(run_lite_seed, "check_snapshot", lambda s: "f" * 64)
    monkeypatch.setattr(run_lite_seed, "check_lock", lambda *a: dict(SETUP))
    oracle = tmp_path / "oracle.json"
    oracle.write_text(json.dumps(ORACLE))
    spec = {**spec, "data_ver": "nasa-toi@" + "f" * 64}
    cmds = {"arm_a_cmd": script(tmp_path, "fa.py", FAKE_A), "arm_b_cmd": script(tmp_path, "fb.py", FAKE_B) + " -p {prompt}"}
    return spec, tmp_path / "bench-lite", str(oracle), cmds


def test_refuses_an_unpinned_snapshot(spec):  # noqa: F811
    with pytest.raises(SystemExit, match="not pinned"):
        run_lite_seed.check_snapshot({**spec, "data_ver": "nasa-toi@PIN_AFTER_FETCH"})


def test_arm_order_alternates():
    assert run_lite_seed.arm_order(1, ["A", "B"]) == ["A", "B"]
    assert run_lite_seed.arm_order(2, ["A", "B"]) == ["B", "A"]


def test_one_seed_writes_both_arms_and_the_command(lite):
    spec_, out, oracle, cmds = lite
    s = run_lite_seed.run_seed(1, spec_, str(out), oracle, argv=["python", "bench/run_lite_seed.py", "--seed", "1"], **cmds)
    seed_dir = out / "seed-1"
    for arm in ("A", "B"):
        assert (seed_dir / arm / "events.jsonl").exists() and (seed_dir / arm / "ledger.db").exists()
    cmd = json.loads((seed_dir / "command.json").read_text())
    assert cmd["command"] == "python bench/run_lite_seed.py --seed 1" and cmd["snapshot_sha256"] == "f" * 64
    assert cmd["packages"]["scikit-learn"] and cmd["packages"]["numpy"]
    assert cmd["lock"]["model"] == "model-x" and cmd["model"] == "model-x" and not cmd["git_dirty"]
    saved = json.loads((seed_dir / "summary.json").read_text())
    assert saved == json.loads(json.dumps(s, default=str))
    assert saved["cost"].startswith("n/a") and "semi-synthetic" in saved["framing"]
    assert saved["episodes"]["A"]["metrics"]["correct"] is False and saved["episodes"]["B"]["metrics"]["correct"] is True

    with pytest.raises(SystemExit, match="never re-run"):
        run_lite_seed.run_seed(1, spec_, str(out), oracle, **cmds)


def test_a_crashed_launch_is_kept(lite):
    spec_, out, oracle, cmds = lite
    bad = {k: v for k, v in spec_.items() if k != "usd_cap"}  # missing placeholder: the launch fails
    s = run_lite_seed.run_seed(2, bad, str(out), oracle, arms=("A",), **cmds)
    assert s["episodes"]["A"]["outcome"] == "launch_failed" and "USD_CAP" in s["episodes"]["A"]["error"]


def test_aggregate_uses_the_fixed_claim_and_labels(lite, tmp_path):
    spec_, out, oracle, cmds = lite
    for seed in (1, 2, 3):
        run_lite_seed.run_seed(seed, spec_, str(out), oracle, **cmds)
    shutil.rmtree(out / "seed-3" / "B")  # a B episode that never produced anything stays in the denominator
    prelock = tmp_path / "prelock.json"
    prelock.write_text(json.dumps({"checks": {"lockable": False}}))
    aggregate_lite.main(["--out", str(out), "--oracle", oracle, "--prelock", str(prelock)])
    md = (out / "report.md").read_text()
    assert "in a lite benchmark (n=3 seeds), FORGE vs a single-agent baseline on this TESS task" in md
    assert "semi-synthetic, preliminary, protocol not lockable" in md and "Cost: n/a" in md
    assert "setup differs" not in md
    rep = json.loads((out / "report.json").read_text())
    pooled = rep["comparison"]["pooled"]
    assert pooled["B"]["episodes"] == 3 and pooled["B"]["completed"] == 2
    assert pooled["A"]["correct"][:2] == [0, 3] and pooled["B"]["correct"][:2] == [2, 3]


def test_labels():
    assert aggregate_lite.labels({"checks": {"lockable": True}}) == ["semi-synthetic", "preliminary"]
    assert aggregate_lite.labels(None) == ["semi-synthetic", "preliminary", "protocol not lockable"]


def test_secrets_are_never_saved(lite, monkeypatch, tmp_path):
    spec_, out, oracle, cmds = lite
    monkeypatch.setenv("FORGE_API_TOKEN", SECRETS[0])
    monkeypatch.setenv("FORGE_SOMETHING", SECRETS[2])           # unknown FORGE_* names are redacted too
    monkeypatch.setenv("FORGE_TESS_CSV", str(tmp_path / "toi.csv"))  # allowlisted paths are kept
    a_cmd = f"env GH_TOKEN={SECRETS[1]} " + cmds["arm_a_cmd"]
    argv = ["python", "bench/run_lite_seed.py", "--seed", "1", "--arm-a-cmd", a_cmd]
    run_lite_seed.run_seed(1, spec_, str(out), oracle, argv=argv, arm_a_cmd=a_cmd, arm_b_cmd=cmds["arm_b_cmd"])
    cmd = json.loads((out / "seed-1" / "command.json").read_text())
    assert cmd["env"]["FORGE_API_TOKEN"] == "<redacted>" and cmd["env"]["FORGE_SOMETHING"] == "<redacted>"
    assert cmd["env"]["FORGE_TESS_CSV"] == str(tmp_path / "toi.csv")
    assert json.loads((out / "seed-1" / "summary.json").read_text())["episodes"]["A"]["outcome"] == "completed"
    for root, _, files in os.walk(out):
        for name in files:
            data = open(os.path.join(root, name), "rb").read()
            for secret in SECRETS:
                assert secret.encode() not in data, f"{secret} saved in {name}"


@pytest.mark.parametrize("text", [
    "ANTHROPIC_API_KEY=sk-ant-abc123456789", "Authorization: Bearer abcdefghijkl", "--api-key abcdefgh123",
    "https://x-access-token:ghs_abcdefgh12345@github.com/o/r.git", "github_pat_ABCDEFGH12345678", "PASSWORD='p a s s'",
])
def test_redact_text(text):
    import redact
    out = redact.redact_text(text)
    assert "<redacted>" in out
    for part in ("sk-ant-abc", "abcdefghijkl", "abcdefgh123", "ghs_abcdefgh", "ABCDEFGH1234", "p a s s"):
        assert part not in out


def _lock_file(tmp_path, lock):
    path = tmp_path / "lite_lock.json"
    path.write_text(json.dumps(lock))
    return str(path)


def test_lock_must_be_written_first(tmp_path):
    lock = {**LOCK, "model": "PIN"}
    with pytest.raises(SystemExit, match="not written yet"):
        run_lite_seed.check_lock(lock, _lock_file(tmp_path, lock), "f" * 64, None)


@pytest.mark.parametrize("change, match", [
    ({"tree_clean": False}, "uncommitted"),
    ({"code_matches": False}, "differs from the locked commit"),
    ({"omni": "0.17.0"}, "omni 0.17.0 != locked 0.16.0"),
    ({"sha": "e" * 64}, "snapshot"),
    ({"model": "other-model"}, "--model other-model != locked model-x"),
])
def test_lock_refuses_a_different_setup(tmp_path, monkeypatch, change, match):
    monkeypatch.setattr(run_lite_seed, "tree_clean", lambda: change.get("tree_clean", True))
    monkeypatch.setattr(run_lite_seed, "code_matches", lambda *a: change.get("code_matches", True))
    monkeypatch.setattr(run_lite_seed, "omni_version", lambda: change.get("omni", "0.16.0"))
    with pytest.raises(SystemExit, match=match):
        run_lite_seed.check_lock(LOCK, _lock_file(tmp_path, LOCK), change.get("sha", "f" * 64), change.get("model"))


def test_lock_passes_on_the_same_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(run_lite_seed, "tree_clean", lambda: True)
    monkeypatch.setattr(run_lite_seed, "omni_version", lambda: "0.16.0")
    head = run_lite_seed._git("rev-parse", "HEAD")
    lock = {**LOCK, "code_commit": head}
    setup = run_lite_seed.check_lock(lock, _lock_file(tmp_path, lock), "f" * 64, None)
    assert setup["model"] == "model-x" and setup["head_commit"] == head  # real git diff of HEAD against itself


def test_aggregate_flags_a_setup_mismatch(lite, monkeypatch, tmp_path):
    spec_, out, oracle, cmds = lite
    run_lite_seed.run_seed(1, spec_, str(out), oracle, **cmds)
    monkeypatch.setattr(run_lite_seed, "check_lock", lambda *a: {**SETUP, "omni_version": "0.17.0"})
    run_lite_seed.run_seed(2, spec_, str(out), oracle, **cmds)
    aggregate_lite.main(["--out", str(out), "--oracle", oracle, "--prelock", str(tmp_path / "none.json")])
    assert "setup differs across seeds" in (out / "report.md").read_text()


def test_fixture_runs_are_never_labelled_as_tess(lite, tmp_path):
    spec_, out, oracle, cmds = lite
    fixture = {**spec_, "data_ver": "synthetic-fixture@" + "f" * 64}
    s = run_lite_seed.run_seed(1, fixture, str(out), oracle, **cmds)
    assert "NOT the TESS snapshot" in s["framing"]
    aggregate_lite.main(["--out", str(out), "--oracle", oracle, "--prelock", str(tmp_path / "none.json")])
    md = (out / "report.md").read_text()
    assert "synthetic TESS-like fixture" in md and "synthetic fixture, not TESS data" in md
    assert "on this TESS task" not in md


def test_ground_truth_is_hidden_while_agents_run(lite, tmp_path, monkeypatch):
    spec_, out, oracle, cmds = lite
    truth = tmp_path / "tess_prelock"
    truth.mkdir()
    (truth / "oracle.json").write_text("{}")
    seen = []
    real = run_lite_seed.launch_arm_a.launch
    def spy(*a, **k):
        seen.append(truth.exists())
        return real(*a, **k)
    monkeypatch.setattr(run_lite_seed, "HIDDEN_DURING_EPISODES", (str(truth),))
    monkeypatch.setattr(run_lite_seed.launch_arm_a, "launch", spy)
    run_lite_seed.run_seed(1, spec_, str(out), oracle, arms=("A",), **cmds)
    assert seen == [False] and (truth / "oracle.json").exists()  # hidden during the episode, restored after


def test_oracle_mentions_are_flagged(tmp_path):
    (tmp_path / "agent_stdout.log").write_text("ran python tools/tess_bias_run.py --oracle out.json")
    assert run_lite_seed.leak_check(str(tmp_path)) == ["agent_stdout.log: --oracle"]
    assert run_lite_seed.leak_check(str(tmp_path / "missing")) == []


def test_arm_b_is_told_how_to_run_the_shared_runner():
    import launch_arm_b
    spec_ = json.load(open(run_lite_seed.DEFAULT_SPEC))
    msg = launch_arm_b.task_message(spec_, "B-1", seed=2)
    assert "### Running an experiment" in msg
    assert ".venv/bin/python tools/tess_bias_run.py --model <lr|hgb> --estimator <naive|iw|iw_clip> --gamma <0|1|2> --seed 2" in msg
