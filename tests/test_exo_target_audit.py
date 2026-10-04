import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import audit_exo_target_feasibility as audit  # noqa: E402


def koi(kepoi_name, disposition, kepid="1"):
    return {"kepoi_name": kepoi_name, "koi_disposition": disposition, "kepid": kepid}


def toi_row(toi_id, disp, tid="100", created="2019-01-01 00:00:00", alias="TOI-1"):
    return {
        "toi": toi_id,
        "tid": tid,
        "tfopwg_disp": disp,
        "toi_created": created,
        "ctoi_alias": alias,
        "sectors": "1",
    }


def test_disposition_counts_normalizes_and_sorts():
    rows = [koi("K1", "confirmed"), koi("K2", "FALSE POSITIVE"), koi("K3", ""), koi("K4", "CANDIDATE")]
    assert audit.disposition_counts(rows) == {
        "(blank)": 1,
        "CANDIDATE": 1,
        "CONFIRMED": 1,
        "FALSE POSITIVE": 1,
    }


def test_objects_already_labeled_at_early_release_are_excluded():
    early = [koi("K1", "CONFIRMED"), koi("K2", "FALSE POSITIVE"), koi("K3", "CANDIDATE")]
    late = [koi("K1", "CONFIRMED"), koi("K2", "FALSE POSITIVE"), koi("K3", "CONFIRMED")]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["cohort_at_early_release"] == 1
    assert fate["outcome_counts"] == {"CONFIRMED": 1}


def test_unresolved_at_later_release_is_censored_not_a_positive():
    early = [koi("K1", "CANDIDATE"), koi("K2", "CANDIDATE")]
    late = [koi("K1", "CONFIRMED"), koi("K2", "CANDIDATE")]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["resolved_positive_confirmed"] == 1
    assert fate["censored_still_unresolved"] == 1
    assert fate["resolved_negative_false_positive"] == 0
    assert fate["usable_labeled_cohort"] == 1


def test_strict_join_is_used_before_kepid_fallback():
    early = [koi("K1", "CANDIDATE", kepid="10"), koi("K2", "CANDIDATE", kepid="20")]
    late = [koi("K1", "CONFIRMED", kepid="10"), koi("K9", "FALSE POSITIVE", kepid="20")]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["outcome_counts"] == {"CONFIRMED": 1, "FALSE POSITIVE": 1}
    assert fate["join_attrition"]["strict_kepoi_name_matches"] == 1
    assert fate["join_attrition"]["kepid_only_matches"] == 1


def test_ambiguous_kepid_matches_are_excluded_not_assigned():
    early = [koi("K1", "CANDIDATE", kepid="20")]
    late = [koi("K8", "CONFIRMED", kepid="20"), koi("K9", "FALSE POSITIVE", kepid="20")]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["ambiguous_kepid_excluded"] == 1
    assert fate["outcome_counts"] == {}
    assert fate["usable_labeled_cohort"] == 0


def test_unmatchable_objects_are_excluded():
    early = [koi("K1", "CANDIDATE", kepid="999")]
    late = [koi("K2", "CONFIRMED", kepid="111")]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["unmatchable_excluded"] == 1
    assert fate["outcome_counts"] == {}


def test_feasibility_flag_requires_both_classes_above_minimum():
    early = [koi(f"K{i}", "CANDIDATE", kepid=str(i)) for i in range(5)]
    late = [koi(f"K{i}", "FALSE POSITIVE", kepid=str(i)) for i in range(5)]
    fate = audit.cohort_fate(early, late, "CANDIDATE")
    assert fate["feasible"] is False
    assert fate["resolved_positive_confirmed"] == 0


def test_confirmed_trend_analysis_reports_net_change_not_a_boolean():
    releases = {
        "Q1_Q16_KOI": [koi(f"K{i}", "CONFIRMED", kepid=str(i)) for i in range(10)],
        "CUMULATIVE": [koi(f"K{i}", "CONFIRMED", kepid=str(i)) for i in range(11)],
    }
    analysis = audit.confirmed_trend_analysis(releases)
    assert analysis["net_confirmed_change"] == 1
    assert analysis["confirmed_band_after_baseline"] == [10, 11]
    assert analysis["baseline_confirmed_share"] == 1.0


def test_confirmed_trend_analysis_handles_empty_baseline():
    analysis = audit.confirmed_trend_analysis({})
    assert analysis["net_confirmed_change"] == 0
    assert analysis["net_confirmed_change_percent"] == 0.0


def test_toi_cohort_splits_resolved_classes_and_censors_the_rest():
    rows = [
        toi_row("1", "KP", tid="100"),
        toi_row("2", "CP", tid="101"),
        toi_row("3", "FP", tid="102"),
        toi_row("4", "PC", tid="103"),
        toi_row("5", "APC", tid="104"),
        toi_row("6", "FA", tid="105"),
        toi_row("7", "", tid="106"),
    ]
    cohort = audit.toi_cohort(rows)
    assert cohort["resolved_positive_kp_or_cp"] == 2
    assert cohort["resolved_negative_fp"] == 1
    assert cohort["censored_pc_apc_fa"] == 3
    assert cohort["blank_disposition"] == 1
    assert cohort["usable_labeled_cohort"] == 3
    assert cohort["feasible_for_binary_outcome"] is False


def test_toi_cohort_flags_ctoi_alias_as_non_independent():
    rows = [toi_row("1", "KP"), toi_row("2", "FP", alias="")]
    cohort = audit.toi_cohort(rows)
    assert cohort["ctoi_alias_is_independent_reference_standard"] is False
    assert cohort["ctoi_alias_present_by_state"]["KP"] == {"yes": 1}


def test_toi_cohort_counts_hosts_not_rows_for_disjointness():
    rows = [
        toi_row("1", "KP", tid="100"),
        toi_row("2", "FP", tid="100"),
        toi_row("3", "FP", tid="200"),
    ]
    cohort = audit.toi_cohort(rows)
    assert cohort["resolved_tois_per_host_histogram"] == {"1": 1, "2": 1}
    assert cohort["multi_toi_hosts_in_resolved_cohort"] == 1
    assert cohort["distinct_hosts_tid_in_resolved_cohort"] == 2
    assert cohort["usable_labeled_cohort"] == 3


def test_build_report_verdict_closes_kepler_and_gates_on_class_size():
    releases = {
        "Q1_Q6_KOI": [koi("K1", "CONFIRMED")],
        "Q1_Q8_KOI": [koi("K1", "CONFIRMED")],
        "Q1_Q12_KOI": [koi("K1", "CONFIRMED")],
        "Q1_Q16_KOI": [koi("K1", "CANDIDATE")],
        "Q1_Q17_DR24_KOI": [koi("K1", "CANDIDATE")],
        "Q1_Q17_DR25_KOI": [koi("K1", "CANDIDATE")],
        "CUMULATIVE": [koi("K1", "CANDIDATE")],
    }
    report = audit.build_report(releases, {"t": "hash"}, None, None, "2026-10-04T00:00:00+00:00")
    assert report["status"] == "TARGET_AVAILABILITY_AUDIT_ONLY_NO_MODEL_NO_METRIC"
    assert report["model_evaluation"] is None
    assert report["verdict"]["kepler_prospective_confirmation_target"] == "NOT_FEASIBLE"
    assert report["toi_candidate_cohort"] is None
    assert all(entry["feasible"] is False for entry in report["cohort_candidates"])


def test_definitions_state_the_censoring_and_outcome_rules():
    releases = {table: [] for table in audit.KOI_RELEASES}
    report = audit.build_report(releases, {}, None, None, "2026-10-04T00:00:00+00:00")
    definitions = report["definitions"]
    assert definitions["unresolved_censored_states"] == ["NOT DISPOSITIONED", "CANDIDATE"]
    assert "never recoded as positives" in definitions["censoring_rule"]
    assert "later than the one supplying features" in definitions["outcome_rule"]
    assert definitions["minimum_usable_class"] == audit.MIN_USABLE_CLASS


def test_fetch_table_retries_then_raises(monkeypatch):
    attempts = []
    sleeps = []

    def fake_urlopen(request, timeout=None):
        attempts.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 429, "slow down", {}, None)

    monkeypatch.setattr(audit.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(audit.ArchiveError):
        audit.fetch_table("cumulative", ("kepoi_name",), retries=3, backoff=7.0, sleep=sleeps.append)
    assert len(attempts) == 3
    assert sleeps == [7.0, 14.0, 21.0]


def test_fetch_table_returns_rows_and_raw_hash(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return self.payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    payload = b"kepoi_name,koi_disposition\nK00001.01,CONFIRMED\nK00002.01,CANDIDATE\n"
    monkeypatch.setattr(
        audit.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(payload)
    )
    rows, digest = audit.fetch_table("cumulative", ("kepoi_name", "koi_disposition"))
    assert [row["kepoi_name"] for row in rows] == ["K00001.01", "K00002.01"]
    assert digest == audit.hashlib.sha256(payload).hexdigest()


def test_committed_artifact_asserts_no_model_result():
    path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "examples", "exo-target-feasibility.json"
    )
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    assert artifact["status"] == "TARGET_AVAILABILITY_AUDIT_ONLY_NO_MODEL_NO_METRIC"
    assert artifact["model_evaluation"] is None
    assert artifact["verdict"]["kepler_prospective_confirmation_target"] == "NOT_FEASIBLE"
    assert artifact["definitions"]["unresolved_censored_states"] == ["NOT DISPOSITIONED", "CANDIDATE"]
    assert artifact["sha256_raw_csv"]