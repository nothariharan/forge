import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))

import report  # noqa: E402
import stats  # noqa: E402


# ---------------------------------------------------------------- stats


def test_wilson_reference_values():
    lo, hi = stats.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    assert stats.wilson(0, 0) == (None, None)
    assert stats.wilson(0, 10)[0] == 0.0


def test_clopper_pearson_reference_values():
    lo, hi = stats.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.1871, abs=1e-4) and hi == pytest.approx(0.8129, abs=1e-4)
    assert stats.clopper_pearson(0, 10) == (0.0, pytest.approx(0.3085, abs=1e-4))
    assert stats.clopper_pearson(10, 10) == (pytest.approx(0.6915, abs=1e-4), 1.0)
    lo, hi = stats.clopper_pearson(3, 5)
    assert lo == pytest.approx(0.1466, abs=1e-4) and hi == pytest.approx(0.9473, abs=1e-4)


def test_paired_bootstrap_is_deterministic_and_bounds_estimate():
    pairs = [(1.0, 2.0), (2.0, 3.0), (3.0, 5.0), (2.0, 2.5), (1.5, 3.0)]
    r1 = stats.paired_bootstrap(pairs, kind="diff", seed=7)
    r2 = stats.paired_bootstrap(pairs, kind="diff", seed=7)
    assert r1 == r2
    assert r1["estimate"] == 1.0  # median of [1, 1, 2, 0.5, 1.5]
    assert r1["ci"][0] <= r1["estimate"] <= r1["ci"][1]
    assert r1["distinct_resamples"] == 126


def test_paired_bootstrap_ratio_drops_zero_baseline():
    r = stats.paired_bootstrap([(0.0, 3.0), (2.0, 4.0), (1.0, 3.0)], kind="ratio")
    assert r["dropped"] == 1 and r["n_pairs"] == 2 and r["estimate"] == 2.5


# ---------------------------------------------------------------- report fixtures


def _write_episode(root, arm, seed, events, usage=None, citations=None, answer=None, metric="auc"):
    d = root / arm / f"seed-{seed}"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"arm": arm, "seed": seed, "metric_name": metric}))
    lines = []
    for i, (ts, typ, payload) in enumerate(events, start=1):
        lines.append(json.dumps({"seq": i, "ts": f"2026-10-04T12:{ts}Z", "run_id": f"{arm}{seed}",
                                 "agent": "x", "type": typ, "payload": payload}))
    (d / "events.jsonl").write_text("\n".join(lines) + "\n")
    if usage is not None:
        (d / "usage.json").write_text(json.dumps(usage))
    if citations is not None:
        (d / "citations.json").write_text(json.dumps({"summary": citations}))
    if answer is not None:
        (d / "answer.json").write_text(json.dumps(answer))


def _experiment(t0, eid, hid, candidate, status="ok", prereg=True, value=0.8):
    ev = []
    if prereg:
        ev.append((f"{t0:02d}:00", "PREDICTION_COMMITTED", {"eid": eid}))
    ev.append((f"{t0:02d}:10", "RUN_STARTED", {"eid": eid, "hid": hid, "candidate": candidate}))
    metrics = {"auc": value} if status == "ok" else {}
    ev.append((f"{t0:02d}:50", "RUN_FINISHED", {"eid": eid, "status": status, "metrics": metrics}))
    return ev


def test_episode_metrics_counts(tmp_path):
    events = [("00:00", "RUN_CREATED", {}), ("01:00", "HYPOTHESIS_PROPOSED", {"hid": "H1"}),
              ("01:30", "HYPOTHESIS_PROPOSED", {"hid": "H2"})]
    events += _experiment(2, "E1", "H1", "c1")                     # valid
    events += _experiment(4, "E2", "H1", "c2", prereg=False)       # prereg violation -> invalid
    events += _experiment(6, "E3", "H2", "c3", status="error")     # failed -> invalid
    events += _experiment(8, "E4", "H2", "best")                   # valid, reaches top
    events += [("09:00", "REPLAN", {"trigger_eid": "E4"}),
               ("10:00", "GATE_OPENED", {"gate_id": "G1"}), ("10:45", "GATE_RESOLVED", {"gate_id": "G1"}),
               ("30:00", "RUN_COMPLETED", {})]
    _write_episode(tmp_path, "B", 1, events,
                   usage={"agents": {"p": {"tokens_in": 100, "tokens_out": 50, "usd": 0.5}, "q": {"tokens_in": 10, "usd": 0.1}}},
                   citations={"references_checked": 4, "unresolvable": 1, "unresolvable_rate": 0.25,
                              "quote_found": 2, "quote_not_in_available_text": 1, "unsupported_quote_rate": 1 / 3},
                   answer={"candidate": "best"})
    m = report.episode_metrics(str(tmp_path / "B" / "seed-1"), {"best": "best", "within_threshold": ["best"]})
    assert m["timed_wall_seconds"] == 1800 and m["completed"]
    assert m["attempts"] == 4 and m["valid_experiments"] == 2 and m["invalid_attempts"] == 2
    assert m["prereg_violations"] == 1
    assert m["hypotheses_proposed"] == 2 and m["hypotheses_tested"] == 2
    assert m["valid_experiments_per_hour"] == pytest.approx(4.0)
    assert m["invalid_attempt_rate"] == 0.5
    assert m["replans_per_valid_experiment"] == 0.5
    assert m["human_seconds"] == 45
    assert m["tokens_total"] == 160 and m["usd"] == pytest.approx(0.6)
    assert m["usd_per_valid_experiment"] == pytest.approx(0.3)
    assert m["experiments_to_top"] == 2 and m["reached_top"] is True and m["correct"] is True
    assert m["quotes_checkable"] == 3


def test_incomplete_episode_uses_budget_cutoff_and_stays_in_denominator(tmp_path):
    events = [("00:00", "RUN_CREATED", {})] + _experiment(2, "E1", "H1", "c1")
    _write_episode(tmp_path, "A", 1, events)
    manifest = tmp_path / "A" / "seed-1" / "manifest.json"
    data = json.loads(manifest.read_text())
    data["budget_end_ts"] = "2026-10-04T12:20:00Z"
    manifest.write_text(json.dumps(data))
    m = report.episode_metrics(str(tmp_path / "A" / "seed-1"), {"within_threshold": ["best"]})
    assert m["completed"] is False and m["timed_wall_seconds"] == 1200
    assert m["reached_top"] is False and m["experiments_to_top"] is None


def test_end_to_end_report(tmp_path):
    (tmp_path / "oracle.json").write_text(json.dumps({"best": "best", "within_threshold": ["best"]}))
    for seed in (1, 2, 3):
        a_events = [("00:00", "RUN_CREATED", {})] + _experiment(5, "E1", "H1", "c1") + [("30:00", "RUN_COMPLETED", {})]
        b_events = ([("00:00", "RUN_CREATED", {})] + _experiment(2, "E1", "H1", "c1")
                    + _experiment(4, "E2", "H2", "best") + [("30:00", "RUN_COMPLETED", {})])
        _write_episode(tmp_path, "A", seed, a_events, usage={"usd": 1.0}, answer={"candidate": "c1"})
        _write_episode(tmp_path, "B", seed, b_events, usage={"usd": 2.0}, answer={"candidate": "best"})

    assert report.main([str(tmp_path)]) == 0
    out = json.loads((tmp_path / "report.json").read_text())
    cmp = out["comparison"]
    assert cmp["paired_seeds"] == [1, 2, 3]
    assert cmp["throughput_multiplier"]["estimate"] == 2.0
    assert cmp["pooled"]["A"]["correct"][:2] == [0, 3] and cmp["pooled"]["B"]["correct"][:2] == [3, 3]
    assert cmp["pooled"]["A"]["reached_top"][:2] == [0, 3]
    assert cmp["metrics"]["experiments_to_top"]["A"] == ["not reached"] * 3
    assert cmp["pooled"]["A"]["invalid_attempts"][2][0] == 0.0
    assert (tmp_path / "A" / "seed-1" / "metrics.json").exists()
    md = (tmp_path / "report.md").read_text()
    assert "Throughput multiplier" in md and "PRELIMINARY" not in md


def test_report_flags_preliminary_with_too_few_seeds(tmp_path):
    for arm in ("A", "B"):
        _write_episode(tmp_path, arm, 1, [("00:00", "RUN_CREATED", {}), ("10:00", "RUN_COMPLETED", {})])
    report.main([str(tmp_path)])
    assert "PRELIMINARY" in (tmp_path / "report.md").read_text()
