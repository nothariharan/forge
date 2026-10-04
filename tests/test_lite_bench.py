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


@pytest.fixture
def lite(spec, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(run_lite_seed, "check_snapshot", lambda s: "f" * 64)
    oracle = tmp_path / "oracle.json"
    oracle.write_text(json.dumps(ORACLE))
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
    assert "semi-synthetic, protocol not lockable" in md and "Cost: n/a" in md
    rep = json.loads((out / "report.json").read_text())
    pooled = rep["comparison"]["pooled"]
    assert pooled["B"]["episodes"] == 3 and pooled["B"]["completed"] == 2
    assert pooled["A"]["correct"][:2] == [0, 3] and pooled["B"]["correct"][:2] == [2, 3]


def test_labels():
    assert aggregate_lite.labels({"checks": {"lockable": True}}) == ["semi-synthetic"]
    assert aggregate_lite.labels(None) == ["semi-synthetic", "protocol not lockable"]
