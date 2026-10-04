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
