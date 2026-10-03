import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))

import oracle  # noqa: E402

SCORES = {"lr": 0.80, "rf": 0.86, "xgb": 0.864, "bad": 0.5}


def fake_runner(task_id, params, seed):
    name = params["model"]
    if name == "broken" and seed == 2:
        raise RuntimeError("diverged")
    base = SCORES.get(name, 0.9)
    return {"metrics": {"auc": base + 0.001 * seed}, "task": task_id}


def make_spec(**overrides):
    spec = {
        "task_id": 31, "metric": "auc", "direction": "maximize", "practical_threshold": 0.005,
        "seeds": [1, 2, 3], "runner": "unused:unused",
        "candidates": [{"id": m, "params": {"model": m}} for m in ("lr", "rf", "xgb", "bad", "broken")],
    }
    spec.update(overrides)
    return spec


def test_sweep_and_oracle(tmp_path):
    spec = make_spec()
    records = oracle.sweep(spec, str(tmp_path), runner=fake_runner, log=lambda *_: None)
    assert len(records) == 15
    o = oracle.build_oracle(spec, records)
    # "broken" scores best on its good seeds but failed seed 2, so it is ineligible.
    assert o["best"] == "xgb"
    assert o["within_threshold"] == ["rf", "xgb"]
    assert o["candidates_complete"] == 4
    broken = next(r for r in o["table"] if r["candidate"] == "broken")
    assert broken["complete"] is False and broken["n_failed"] == 1
    failed = [json.loads(l) for l in open(tmp_path / "sweep_runs.jsonl") if '"error"' in l]
    assert failed and "diverged" in failed[0]["error"]


def test_minimize_direction(tmp_path):
    spec = make_spec(direction="minimize", candidates=[{"id": m, "params": {"model": m}} for m in ("lr", "bad")])
    o = oracle.build_oracle(spec, oracle.sweep(spec, str(tmp_path), runner=fake_runner, log=lambda *_: None))
    assert o["best"] == "bad" and o["within_threshold"] == ["bad"]


def test_resume_skips_completed_pairs_and_ignores_other_specs(tmp_path):
    spec = make_spec(candidates=[{"id": "lr", "params": {"model": "lr"}}])
    calls = []

    def counting(task_id, params, seed):
        calls.append(seed)
        return fake_runner(task_id, params, seed)

    oracle.sweep(spec, str(tmp_path), runner=counting, log=lambda *_: None)
    oracle.sweep(spec, str(tmp_path), runner=counting, log=lambda *_: None)
    assert calls == [1, 2, 3]

    changed = make_spec(candidates=[{"id": "lr", "params": {"model": "lr"}}], practical_threshold=0.01)
    oracle.sweep(changed, str(tmp_path), runner=counting, log=lambda *_: None)
    assert calls == [1, 2, 3, 1, 2, 3]


def test_missing_metric_is_a_failure(tmp_path):
    spec = make_spec(candidates=[{"id": "lr", "params": {"model": "lr"}}])
    records = oracle.sweep(spec, str(tmp_path), runner=lambda *a: {"metrics": {}}, log=lambda *_: None)
    o = oracle.build_oracle(spec, records)
    assert {r["status"] for r in records} == {"missing_metric"} and o["best"] is None


def test_load_spec_validation(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"task_id": 1}))
    with pytest.raises(ValueError, match="missing keys"):
        oracle.load_spec(str(p))
    bad = make_spec(direction="up")
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="direction"):
        oracle.load_spec(str(p))


def test_cli_with_module_runner(tmp_path, monkeypatch):
    pkg = tmp_path / "fake_runner_mod.py"
    pkg.write_text(
        "def run(task_id, params, seed):\n"
        "    return {'metrics': {'auc': {'a': 0.7, 'b': 0.9}[params['m']] + seed * 1e-4}}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = make_spec(runner="fake_runner_mod:run", candidates=[{"id": "a", "params": {"m": "a"}}, {"id": "b", "params": {"m": "b"}}])
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    out = tmp_path / "bench"
    assert oracle.main([str(spec_path), "--out", str(out)]) == 0
    o = json.loads((out / "oracle.json").read_text())
    assert o["best"] == "b" and o["within_threshold"] == ["b"]
    assert oracle.main([str(spec_path), "--out", str(out), "--aggregate-only"]) == 0
