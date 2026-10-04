"""Tests for tools/tess_bias_run.py on the synthetic fixture (tests/tess_fixture.py). Not real data."""
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(__file__)
sys.path[:0] = [HERE, os.path.join(HERE, "..", "tools")]

import tess_bias_run as tb  # noqa: E402
from tess_fixture import make_fixture  # noqa: E402


@pytest.fixture(scope="module")
def fixture_env(tmp_path_factory):
    path = tmp_path_factory.mktemp("tess") / "toi.csv"
    digest = make_fixture(path, n_hosts=1200, seed=3)
    old = {k: os.environ.get(k) for k in ("FORGE_TESS_CSV", "FORGE_TESS_SHA256")}
    os.environ.update(FORGE_TESS_CSV=str(path), FORGE_TESS_SHA256=digest)
    yield path, digest
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---------------------------------------------------------------- host-level sampling


def _groups(n_hosts=400, seed=0):
    rng = np.random.default_rng(seed)
    sizes = rng.choice([1, 2, 3], size=n_hosts, p=[0.85, 0.1, 0.05])
    groups = np.repeat(np.arange(n_hosts), sizes).astype(str)
    host_e = rng.uniform(0.05, 0.95, n_hosts)
    return groups, np.repeat(host_e, sizes)


@pytest.mark.parametrize("gamma", [0, 1, 2])
def test_host_split_is_well_defined(gamma):
    groups, e = _groups()
    max_host = max(np.unique(groups, return_counts=True)[1])
    for seed in range(20):
        in_r = tb.host_split(groups, e, gamma, 0.30, np.random.default_rng(seed))
        # Share of TOIs is within one host's size of the target.
        assert abs(in_r.sum() - 0.30 * len(groups)) <= max_host
        # No host is split across R* and U*.
        for g in np.unique(groups):
            assert len(set(in_r[groups == g])) == 1


def test_host_split_is_deterministic_per_seed():
    groups, e = _groups()
    a = tb.host_split(groups, e, 1, 0.3, np.random.default_rng(5))
    b = tb.host_split(groups, e, 1, 0.3, np.random.default_rng(5))
    c = tb.host_split(groups, e, 1, 0.3, np.random.default_rng(6))
    assert (a == b).all() and not (a == c).all()


def test_gamma_controls_selection_strength():
    groups, e = _groups(n_hosts=2000)
    sep = {}
    for gamma in (0, 1, 2):
        diffs = []
        for seed in range(30):
            in_r = tb.host_split(groups, e, gamma, 0.3, np.random.default_rng(seed))
            diffs.append(e[in_r].mean() - e[~in_r].mean())
        sep[gamma] = float(np.mean(diffs))
    assert abs(sep[0]) < 0.01  # uniform: R* and U* look alike
    assert sep[0] < sep[1] < sep[2]  # higher gamma: R* holds more high-e hosts


# ---------------------------------------------------------------- data pinning


def test_refuses_wrong_or_missing_hash(fixture_env):
    path, digest = fixture_env
    with pytest.raises(ValueError, match="expected the pinned snapshot"):
        tb.load_rows(path, "0" * 64)
    with pytest.raises(ValueError, match="no pinned snapshot hash"):
        tb.load_rows(path, "")
    rows, got = tb.load_rows(path, digest)
    assert got == digest and rows


def test_labeled_cohort_matches_label_rules(fixture_env):
    path, digest = fixture_env
    prep = tb.prepare(str(path), digest)
    import csv
    states = [r["tfopwg_disp"] for r in csv.DictReader(open(path))]
    assert len(prep["y"]) == sum(s in ("CP", "FP", "FA") for s in states)
    assert prep["y"].sum() == states.count("CP")
    assert prep["n_unresolved"] == sum(s in ("PC", "APC") for s in states)
    assert "pl_eqtlim" not in prep["features"] and "pl_insolsymerr" not in prep["features"]
    assert "toi_created" not in prep["features"] and "tid" not in prep["features"]
    assert ((prep["e"] > 0) & (prep["e"] < 1)).all()


# ---------------------------------------------------------------- runner contract


def test_run_contract(fixture_env):
    out = tb.run(tb.TASK_ID, {"model": "lr", "estimator": "iw", "gamma": 1, "replicates": 4}, seed=2)
    m = out["metrics"]
    assert set(m) >= {"abs_error", "estimate", "true_auc", "naive_auc", "gap", "gap_low", "gap_high"}
    assert all(isinstance(v, float) and math.isfinite(v) for v in m.values())
    assert out["replicate_seeds"] == [2000, 2001, 2002, 2003] and out["replicates_valid"] == 4
    assert out["data_sha256"] == fixture_env[1] and "not accuracy on real unresolved" in out["framing"]
    assert abs(m["share_r"] - 0.30) < 0.01
    # Same seed, same answer: the oracle and the episodes see identical simulated splits.
    assert tb.run(tb.TASK_ID, {"model": "lr", "estimator": "iw", "gamma": 1, "replicates": 4}, seed=2) == out


def test_estimators_share_the_same_replicates(fixture_env):
    a = tb.run(tb.TASK_ID, {"model": "lr", "estimator": "naive", "gamma": 1, "replicates": 4}, seed=3)
    b = tb.run(tb.TASK_ID, {"model": "lr", "estimator": "iw_clip", "gamma": 1, "replicates": 4}, seed=3)
    assert a["metrics"]["true_auc"] == b["metrics"]["true_auc"] and a["metrics"]["gap"] == b["metrics"]["gap"]
    assert a["metrics"]["estimate"] == a["metrics"]["naive_auc"]


@pytest.mark.parametrize("params,match", [
    ({"model": "rf"}, "model must be"), ({"estimator": "x"}, "estimator one of"), ({"gamma": 3}, "gamma must be")])
def test_rejects_params_outside_the_protocol(fixture_env, params, match):
    with pytest.raises(ValueError, match=match):
        tb.run(tb.TASK_ID, params, seed=1)


def test_oracle_decision_rule_shape(fixture_env):
    o = tb.build_oracle(seeds=(1, 2), replicates=3)
    assert o["status"].startswith("SEMI_SYNTHETIC") and o["data_sha256"] == fixture_env[1]
    assert o["gap_gamma1_lr_naive"]["n"] == 6 and o["best"] in o["within_threshold"]
    assert set(o["within_threshold"]) <= set(o["candidates"]) and len(o["candidates"]) == 7
    if o["best"] == tb.NO_CORRECTION:
        assert set(o["within_threshold"]) == {tb.NO_CORRECTION, "lr_naive", "hgb_naive"}
    else:
        assert not any(k.endswith("_naive") for k in o["within_threshold"])
    assert isinstance(o["control_within_bound"], bool)


def _fake_reps(gap, errors):
    """Replicates with a fixed naive gap and per-estimator signed errors (truth = 0.80)."""
    reps = []
    for i in range(10):
        noise = (i - 4.5) * 0.001
        est = {e: 0.80 + d + noise for e, d in errors.items()}
        est["naive"] = 0.80 + gap + noise
        reps.append({"valid": True, "gap": gap + noise, "true_auc": 0.80, "estimates": est})
    return tuple(reps)


def test_oracle_meaningful_gap_picks_a_correcting_estimator(fixture_env, monkeypatch):
    monkeypatch.setattr(tb, "_replicates", lambda path, exp, model, gamma, seed, n, rho, res="lr":
                        _fake_reps(0.05 if gamma == 1.0 else 0.0, {"iw": 0.004, "iw_clip": 0.02}))
    o = tb.build_oracle(seeds=(1,), replicates=10)
    assert o["decision"].startswith("overstated")
    assert o["best"] in ("lr_iw", "hgb_iw") and set(o["within_threshold"]) == {"lr_iw", "hgb_iw"}
    assert o["control_within_bound"]


def test_oracle_small_gap_means_no_correction(fixture_env, monkeypatch):
    monkeypatch.setattr(tb, "_replicates", lambda path, exp, model, gamma, seed, n, rho, res="lr":
                        _fake_reps(0.011 if res == "lr" else 0.04, {"iw": 0.003, "iw_clip": 0.003}))
    o = tb.build_oracle(seeds=(1,), replicates=10)
    assert o["best"] == tb.NO_CORRECTION and o["within_threshold"] == ["hgb_naive", "lr_naive", "no_correction"]
    assert not o["control_within_bound"]  # the control gap of 0.011 breaks the 0.01 bound and is reported
    # The nonlinear sensitivity arm finds a meaningful gap: reported, flagged, decision unchanged.
    sens = o["sensitivity_nonlinear_resolution"]
    assert sens["mean_gap"] > 0.02 and sens["agrees_with_primary"] is False and o["best"] == tb.NO_CORRECTION


# ---------------------------------------------------------------- spec + prompt + arm A integration

import json  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "bench"))
import arm_a  # noqa: E402
import launch_arm_a  # noqa: E402
import launch_arm_b  # noqa: E402
import report  # noqa: E402

SPEC = os.path.join(HERE, "..", "bench", "specs", "tess_resolution_bias.json")


def test_tess_spec_fills_both_prompts():
    spec = launch_arm_a.load_spec(SPEC)
    prompt = launch_arm_a.fill_prompt(spec)
    assert not launch_arm_a.PLACEHOLDER_RE.search(prompt) and "OpenML" not in prompt
    assert "no_correction" in prompt and "hgb_iw_clip" in prompt and "not accuracy on real unresolved" in prompt
    msg = launch_arm_b.task_message(spec, "B-1")
    assert "no_correction" in msg and "### Tools" not in msg  # both arms get the same task and answer options
    options = [o.split(" ")[0].strip(",") for o in spec["answer_options"].split(", ")]
    assert set(options) == set(tb.candidates())  # the allowed answers are exactly the oracle's candidates


def test_arm_a_episode_with_the_real_runner_on_the_fixture(fixture_env, tmp_path):
    spec = launch_arm_a.load_spec(SPEC)
    ep = tmp_path / "A" / "seed-1"
    launch_arm_a.launch(spec, 1, str(ep), run_id="A-tess-1", dry_run=True)
    run = ["--episode", str(ep)]
    arm_a.main(run + ["predict", "--eid", "E1", "--hid", "H1", "--mean", "0.0", "--sd", "0.02", "--falsifier", "gap >= 0.02"])
    arm_a.main(run + ["run", "--eid", "E1", "--hid", "H1", "--candidate", "lr_naive_g1",
                      "--params", json.dumps({"model": "lr", "estimator": "naive", "gamma": 1, "replicates": 3})])
    arm_a.main(run + ["answer", "--candidate", "no_correction"])
    finished = [e for e in arm_a.Episode(str(ep)).events() if e["type"] == "RUN_FINISHED"][0]["payload"]
    assert finished["status"] == "ok" and "gap" in finished["metrics"] and "true_auc" in finished["metrics"]
    oracle = {"best": "no_correction", "within_threshold": ["hgb_naive", "lr_naive", "no_correction"]}
    m = report.episode_metrics(str(ep), oracle)
    assert m["valid_experiments"] == 1 and m["prereg_violations"] == 0 and m["correct"] is True


def test_nonlinear_resolution_model_runs_and_is_recorded(fixture_env):
    out = tb.run(tb.TASK_ID, {"model": "lr", "estimator": "naive", "gamma": 1, "replicates": 3,
                              "resolution_model": "hgb"}, seed=4)
    assert out["resolution_model"] == "hgb" and 0.5 < out["resolution_model_oof_auc"] < 1
    with pytest.raises(ValueError, match="resolution_model must be"):
        tb.run(tb.TASK_ID, {"resolution_model": "rf"}, seed=1)


# ---------------------------------------------------------------- pre-lock run and T1 on a saved snapshot

import shutil  # noqa: E402
import subprocess  # noqa: E402

TOOLS = os.path.join(HERE, "..", "tools")


def test_pin_in_spec_is_the_expected_hash(fixture_env, tmp_path, monkeypatch):
    path, digest = fixture_env
    spec = tmp_path / "spec.json"
    shutil.copy(SPEC, spec)
    monkeypatch.setenv("FORGE_TESS_SPEC", str(spec))
    monkeypatch.delenv("FORGE_TESS_SHA256")
    assert tb.expected_sha256() == ""  # spec still says PIN_AFTER_FETCH, so nothing is pinned
    import tess_prelock
    tess_prelock.pin(spec, digest)
    assert json.loads(spec.read_text())["data_ver"] == f"nasa-toi@{digest}" and tb.expected_sha256() == digest


def test_prelock_on_the_fixture(fixture_env, tmp_path, monkeypatch):
    path, digest = fixture_env
    spec = tmp_path / "spec.json"
    shutil.copy(SPEC, spec)
    monkeypatch.setenv("FORGE_TESS_SPEC", str(spec))
    monkeypatch.delenv("FORGE_TESS_SHA256")
    import tess_prelock
    monkeypatch.setattr(tess_prelock, "OUT", tmp_path / "prelock")
    monkeypatch.setattr(tb, "DEFAULT_REPLICATES", 3)
    monkeypatch.setattr(tb.build_oracle, "__defaults__", ((1, 2), 3))
    code = tess_prelock.main(["--no-fetch", "--skip-t1"])
    summary = json.loads((tmp_path / "prelock" / "summary.json").read_text())
    assert summary["snapshot"]["sha256"] == digest and summary["status"].startswith("PRELOCK_RUN_SEMI_SYNTHETIC")
    assert set(summary["checks"]) >= {"control_within_0.01", "single_decision", "decision_fragile", "sensitivity_agrees", "lockable"}
    assert code == (0 if summary["checks"]["lockable"] else 3)
    assert "sensitivity_nonlinear_resolution" in summary and summary["best"] in summary["within_threshold"]


def test_t1_reruns_on_a_saved_csv_and_checks_its_hash(fixture_env, tmp_path):
    path, digest = fixture_env
    out = tmp_path / "t1.json"
    base = [sys.executable, os.path.join(TOOLS, "tess_resolution_shift.py"), "--csv", str(path),
            "--bootstrap", "20", "--skip-permutation", "--output", str(out)]
    ok = subprocess.run(base + ["--expect-sha256", digest], capture_output=True, text=True, timeout=110)
    assert ok.returncode == 0, ok.stderr[-500:]
    t1 = json.loads(out.read_text())
    assert t1["sha256_raw_csv"] == digest and "saved copy" in t1["data_source"]
    bad = subprocess.run(base + ["--expect-sha256", "0" * 64], capture_output=True, text=True, timeout=60)
    assert bad.returncode != 0 and "expected" in bad.stderr
