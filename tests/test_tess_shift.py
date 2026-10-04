import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import tess_resolution_shift as shift  # noqa: E402

ALL_COLUMNS = [
    "toi",
    "tid",
    "tfopwg_disp",
    "toipfx",
    "sectors",
    "toi_created",
    "rowupdate",
    "release_date",
    "pl_orbper",
    "pl_orbpererr1",
    "pl_rade",
    "pl_eqt",
    "pl_eqtlim",
    "pl_insolsymerr",
    "st_teff",
    "st_rad",
    "ra",
    "dec",
]


def row(state, tid, orbper="2.0", rade="2.5", teff="5500", created="2020-01-01 00:00:00"):
    return {
        "toi": f"T{tid}",
        "tid": str(tid),
        "tfopwg_disp": state,
        "toipfx": "",
        "sectors": "1",
        "toi_created": created,
        "rowupdate": created,
        "release_date": created,
        "pl_orbper": orbper,
        "pl_orbpererr1": "0.01",
        "pl_rade": rade,
        "pl_eqt": "",
        "pl_eqtlim": "",
        "pl_insolsymerr": "",
        "st_teff": teff,
        "st_rad": "1.0",
        "ra": "10.0",
        "dec": "-5.0",
    }


def test_to_float_handles_blank_and_non_numeric():
    assert shift.to_float("1.5") == 1.5
    assert np.isnan(shift.to_float(""))
    assert np.isnan(shift.to_float("2020-01-01 00:00:00"))
    assert np.isnan(shift.to_float(None))


def test_parse_timestamp_days_returns_numeric_offset():
    zero = shift.parse_timestamp_days("2018-01-01 00:00:00")
    later = shift.parse_timestamp_days("2018-01-11 00:00:00")
    assert zero == 0.0
    assert later == 10.0
    assert np.isnan(shift.parse_timestamp_days(""))
    assert np.isnan(shift.parse_timestamp_days("not-a-date"))


def test_timestamp_columns_are_numeric_in_the_sensitivity_arm():
    """A string timestamp must not silently become an all-NaN column."""
    rows = shift.add_timestamp_features([row("CP", 1)])
    assert rows[0][shift.TIMESTAMP_DERIVED["toi_created"]] == "730.0"


def test_primary_arm_excludes_timestamps_and_labels():
    features, excluded = shift.select_feature_columns(ALL_COLUMNS, include_timestamps=False)
    assert shift.TIMESTAMP_DERIVED["toi_created"] not in features
    assert "toi_created" not in features
    assert excluded["tfopwg_disp"] == "identifier or label"
    assert excluded["toi"] == "identifier or label"
    assert "timestamp" in excluded["toi_created"]
    assert "pl_eqtlim" in excluded
    assert "pl_insolsymerr" in excluded
    assert "ra" in excluded
    assert "pl_orbper" in features
    assert "st_teff" in features


def test_sensitivity_arm_adds_numeric_timestamp_offsets():
    features, excluded = shift.select_feature_columns(ALL_COLUMNS, include_timestamps=True)
    for derived in shift.TIMESTAMP_DERIVED.values():
        assert derived in features
    assert "converted to a numeric day offset" in excluded["toi_created"]


def test_drop_empty_columns_removes_all_nan_only():
    matrix = np.array([[1.0, np.nan], [2.0, np.nan]])
    kept_matrix, kept, dropped = shift.drop_empty_columns(matrix, ["a", "b"])
    assert kept == ["a"]
    assert dropped == ["b"]
    assert kept_matrix.shape == (2, 1)


def test_build_arrays_maps_states_and_drops_others():
    rows = [row("CP", 1), row("FP", 2), row("PC", 3), row("APC", 4), row("KP", 5), row("", 6)]
    features, _ = shift.select_feature_columns(ALL_COLUMNS)
    matrix, y, groups, dropped, host_counts = shift.build_arrays(
        rows, features, shift.RESOLVED_STATES, shift.UNRESOLVED_STATES
    )
    assert list(y) == [1, 1, 0, 0]
    assert list(groups) == ["1", "2", "3", "4"]
    assert dropped["state_KP"] == 1
    assert dropped["state_(blank)"] == 1
    assert len(host_counts) == 4


def test_build_arrays_counts_hosts_with_several_candidates():
    rows = [row("CP", 1), row("PC", 1), row("FP", 2)]
    features, _ = shift.select_feature_columns(ALL_COLUMNS)
    _, _, _, _, host_counts = shift.build_arrays(
        rows, features, shift.RESOLVED_STATES, shift.UNRESOLVED_STATES
    )
    assert host_counts == {"1": 2, "2": 1}


def test_build_arrays_parses_numeric_features_and_marks_blanks_nan():
    rows = [row("CP", 1, orbper="3.5", teff="")]
    features, _ = shift.select_feature_columns(ALL_COLUMNS)
    matrix, _, _, _, _ = shift.build_arrays(
        rows, features, shift.RESOLVED_STATES, shift.UNRESOLVED_STATES
    )
    assert matrix[0][features.index("pl_orbper")] == 3.5
    assert np.isnan(matrix[0][features.index("st_teff")])


def test_cluster_bootstrap_recovers_separation_on_planted_signal():
    rng = np.random.default_rng(0)
    n = 200
    y = np.array([0, 1] * (n // 2))
    groups = np.arange(n).astype(str)
    scores = np.clip(y * 0.8 + rng.normal(0, 0.1, n), 0, 1)
    result = shift.cluster_bootstrap_auc(y, scores, groups, n_boot=200, seed=0)
    assert result["n_effective"] > 0
    assert result["ci95_low"] > 0.5


def test_run_arm_finds_no_shift_when_features_carry_no_signal():
    rng = np.random.default_rng(1)
    rows = []
    for i in range(400):
        state = "CP" if i % 2 == 0 else "PC"
        rows.append(row(state, i, orbper=f"{rng.normal(10, 3):.4f}", rade=f"{rng.normal(3, 1):.4f}"))
    arm = shift.run_arm(
        rows,
        ALL_COLUMNS,
        "synthetic_null",
        False,
        shift.RESOLVED_STATES,
        shift.UNRESOLVED_STATES,
        n_bootstrap=200,
        n_permutations=2,
        seed=0,
    )
    assert arm["n_rows"] == 400
    assert 0.3 < arm["oof_auc"] < 0.7
    assert arm["prediction_supported"] is False


def test_run_arm_detects_shift_when_feature_encodes_the_label():
    rows = []
    for i in range(80):
        state = "CP" if i % 2 == 0 else "PC"
        radius = "9.0" if state == "CP" else "1.0"
        rows.append(row(state, i, rade=radius))
    arm = shift.run_arm(
        rows,
        ALL_COLUMNS,
        "synthetic_shift",
        False,
        shift.RESOLVED_STATES,
        shift.UNRESOLVED_STATES,
        n_bootstrap=60,
        n_permutations=2,
        seed=0,
    )
    assert arm["oof_auc"] > 0.9
    assert arm["prediction_supported"] is True
    assert arm["falsifier_triggered"] is False
    assert arm["cluster_bootstrap_auc"]["ci95_low"] > 0.5


def test_run_arm_records_dropped_all_missing_columns():
    rows = [row("CP", i) for i in range(10)] + [row("PC", 100 + i) for i in range(10)]
    arm = shift.run_arm(
        rows,
        ALL_COLUMNS,
        "synthetic",
        False,
        shift.RESOLVED_STATES,
        shift.UNRESOLVED_STATES,
        n_bootstrap=20,
        n_permutations=1,
        seed=0,
    )
    assert "pl_eqt" in arm["columns_dropped_all_missing"]
    assert arm["n_features"] < arm["n_features_requested"]


def test_committed_artifact_matches_the_preregistered_verdict():
    path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "examples", "tess-resolution-shift.json"
    )
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    assert artifact["status"] == "SHIFT_MEASUREMENT_ONLY_NOT_VETTING_ACCURACY_NOT_BENCHMARK_EVIDENCE"
    assert artifact["preregistration"].endswith("TESS_RESOLUTION_SHIFT_PREREGISTRATION.md")
    primary = artifact["arms"][0]
    assert primary["arm"] == "primary_cp_fp_vs_pc_apc"
    assert primary["includes_timestamp_columns"] is False
    assert primary["n_features"] > 0
    assert len(primary["oof_auc_per_seed"]) == len(artifact["protocol"]["seeds"])
    assert artifact["verdict"]["shift_detected"] is True
    assert artifact["verdict"]["falsifier_triggered"] is False
    bootstrap = primary["cluster_bootstrap_auc"]
    assert bootstrap["ci95_low"] > 0.5
    null = artifact["permutation_null_primary_arm"]
    assert null["max"] < primary["oof_auc"]
    assert artifact["environment"]["python"]