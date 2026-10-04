import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import audit_tess_reference_standard as ref  # noqa: E402


def toi(state, tid, toi_id="T", created="2020-01-01 00:00:00"):
    return {
        "toi": toi_id,
        "tid": str(tid),
        "tfopwg_disp": state,
        "toi_created": created,
        "toipfx": "",
        "sectors": "1",
    }


def ps(tic, year, name="P b", host="H", method="Transit"):
    return {
        "pl_name": name,
        "hostname": host,
        "tic_id": tic,
        "disc_year": str(year),
        "discoverymethod": method,
    }


def test_normalize_tic_handles_formatted_and_bare_ids():
    assert ref.normalize_tic("TIC 281461362") == "281461362"
    assert ref.normalize_tic("281461362") == "281461362"
    assert ref.normalize_tic("  TIC 281461362 ") == "281461362"
    assert ref.normalize_tic("") == ""
    assert ref.normalize_tic(None) == ""


def test_normalize_tic_keeps_short_ids_that_really_exist():
    assert ref.normalize_tic("TIC 9989136") == "9989136"
    assert len(ref.normalize_tic("TIC 9989136")) != 9


def test_match_rate_separates_confirmed_from_false_positive():
    rows = [
        toi("CP", 100),
        toi("CP", 101),
        toi("FP", 200),
        toi("FP", 201),
        toi("PC", 300),
    ]
    rates = ref.match_rates_by_state(rows, {"100", "101"})
    assert rates["CP"]["match_rate"] == 1.0
    assert rates["FP"]["match_rate"] == 0.0
    assert rates["PC"]["match_rate"] == 0.0
    assert rates["CP"]["toi_rows"] == 2


def test_match_rate_is_not_defeated_by_string_prefixed_reference_ids():
    rows = [toi("CP", 281461362)]
    rates = ref.match_rates_by_state(rows, {ref.normalize_tic("TIC 281461362")})
    assert rates["CP"]["match_rate"] == 1.0


def test_identifier_diagnostics_applies_no_digit_length_filter():
    rows = [toi("CP", 9989136), toi("FP", 281461362), toi("PC", 12345)]
    confirmed = {"9989136"}
    diag = ref.identifier_diagnostics(rows, confirmed)
    assert sum(diag["toi_tid_digit_length_histogram"].values()) == 3
    assert diag["matched_digit_length_histogram"] == {"7": 1}
    assert diag["matched_rows_by_state"] == {"CP": 1}


def test_multi_candidate_hosts_are_counted_and_mixed_hosts_flagged():
    rows = [
        toi("CP", 100, "A"),
        toi("CP", 100, "B"),
        toi("CP", 100, "C"),
        toi("CP", 200, "D"),
        toi("FP", 300, "E"),
        toi("FP", 300, "F"),
        toi("CP", 300, "G"),
    ]
    result = ref.resolved_hosts_with_multiple_candidates(rows)
    assert result["hosts_with_multiple_resolved_candidates"] == 2
    assert result["hosts_mixing_positive_and_negative_candidates"] == 1


def test_disc_year_agreement_separates_cp_from_kp():
    rows = [toi("CP", 100), toi("CP", 101), toi("KP", 200)]
    ps_rows = [ps("TIC 100", 2019), ps("TIC 101", 2020), ps("TIC 200", 2010)]
    agreement = ref.disc_year_agreement(rows, ps_rows)
    assert agreement["CP"]["hosts_matched"] == 2
    assert agreement["CP"]["min_disc_year_in_tess_era"] == 2
    assert agreement["KP"]["min_disc_year_pre_tess"] == 1


def test_label_semantics_reports_kp_and_fa_variants():
    rows = [toi("CP", i) for i in range(300)] + [toi("FP", 1000 + i) for i in range(300)]
    rows += [toi("KP", 2000 + i) for i in range(100)] + [toi("FA", 3000) for i in range(5)]
    semantics = ref.label_semantics(rows)
    variants = semantics["positive_class_variants"]
    assert variants["exclude_kp"]["positive"] == 300
    assert variants["kp_and_cp_as_positive"]["positive"] == 400
    fa = semantics["fa_handling_variants"]
    assert fa["fa_as_negative"]["negative"] == 305
    assert fa["fa_as_censored"]["negative"] == 300


def test_label_semantics_recommends_cp_plus_fp_and_fa():
    rows = [toi("CP", i) for i in range(5)] + [toi("FP", 100 + i) for i in range(5)]
    recommended = ref.label_semantics(rows)["recommended_pending_review"]
    assert recommended["positive_states"] == ["CP"]
    assert recommended["negative_states"] == [ref.NEGATIVE_STATE, ref.FA_STATE]


def test_build_report_gate_passes_on_separated_reference_standard():
    toi_rows = [toi("CP", 100 + i) for i in range(250)]
    toi_rows += [toi("FP", 5000 + i) for i in range(250)]
    ps_rows = [ps(f"TIC {100 + i}", 2019) for i in range(250)]
    report = ref.build_report(toi_rows, ps_rows, ["tid", "tfopwg_disp"], ["tic_id"], {}, "now")
    assert report["gate"]["verdict"].startswith("PASSES")
    assert report["gate"]["negatives_remain_unadjudicated"] is True
    assert report["model_evaluation"] is None


def test_build_report_gate_fails_when_control_rate_is_not_separated():
    toi_rows = [toi("CP", 100 + i, f"C{i}") for i in range(250)]
    toi_rows += [toi("FP", 100 + i, f"F{i}") for i in range(250)]
    ps_rows = [ps(f"TIC {100 + i}", 2019) for i in range(250)]
    report = ref.build_report(toi_rows, ps_rows, ["tid"], ["tic_id"], {}, "now")
    assert report["cross_match"]["match_rate_by_state"]["CP"]["match_rate"] == 1.0
    assert report["cross_match"]["match_rate_by_state"]["FP"]["match_rate"] == 1.0
    assert report["gate"]["verdict"] == "FAILS"


def test_build_report_records_absence_of_disposition_date():
    toi_rows = [toi("CP", 100)]
    ps_rows = [ps("TIC 100", 2019)]
    columns = ["tid", "tfopwg_disp", "toi_created", "rowupdate", "release_date"]
    report = ref.build_report(toi_rows, ps_rows, columns, ["tic_id"], {}, "now")
    assert report["disposition_date_column_present"] is False
    assert report["gate"]["prospective_temporal_split_possible"] is False
    assert set(report["toi_date_like_columns"]) == {"toi_created", "rowupdate", "release_date"}


def test_fetch_table_retries_with_backoff_then_raises(monkeypatch):
    attempts = []
    sleeps = []

    def fake_urlopen(request, timeout=None):
        attempts.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)

    monkeypatch.setattr(ref.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ref.ArchiveError):
        ref.fetch_table("toi", ("tid",), retries=3, backoff=5.0, sleep=sleeps.append)
    assert len(attempts) == 3
    assert sleeps == [5.0, 10.0, 15.0]


def test_committed_artifact_reports_a_passing_positive_gate():
    path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "examples", "tess-reference-standard.json"
    )
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    assert artifact["status"] == "REFERENCE_STANDARD_AUDIT_ONLY_NO_MODEL_NO_METRIC"
    assert artifact["model_evaluation"] is None
    assert artifact["gate"]["verdict"].startswith("PASSES")
    assert artifact["gate"]["negatives_remain_unadjudicated"] is True
    assert artifact["gate"]["prospective_temporal_split_possible"] is False
    assert artifact["ps_has_toi_column"] is False
    assert artifact["cross_match"]["tid_is_tic_id"] is True
    rates = artifact["cross_match"]["match_rate_by_state"]
    assert rates["CP"]["match_rate"] > rates["FP"]["match_rate"]
    assert artifact["sha256_raw_csv"]