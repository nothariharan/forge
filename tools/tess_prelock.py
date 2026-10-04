"""One command for the TESS pre-lock run on a pinned real snapshot (bench/PROTOCOL_TESS.md section 10).

Needs network access to the NASA Exoplanet Archive. Steps:
1. Fetch the TOI table once and save the raw bytes (results/cache/toi.csv).
2. Pin it: write "nasa-toi@<sha256>" into bench/specs/tess_resolution_bias.json (data_ver),
   which tools/tess_bias_run.py reads as the expected hash.
3. Re-run T1 (tools/tess_resolution_shift.py) on that same file.
4. Run the semi-synthetic simulation oracle (decision rule + nonlinear sensitivity arm).
5. Write results/tess_prelock/summary.json with the lock checks.

    python tools/tess_prelock.py            # fetch, pin, T1, oracle
    python tools/tess_prelock.py --no-fetch # reuse an existing results/cache/toi.csv

Everything it produces describes a semi-synthetic mechanism, not accuracy on real unresolved TOIs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import tess_bias_run as tb  # noqa: E402

OUT = Path(__import__("os").environ.get("FORGE_TESS_PRELOCK_OUT", REPO / "results" / "tess_prelock"))


def pin(spec_path: Path, digest: str) -> None:
    spec = json.loads(spec_path.read_text())
    spec["data_ver"] = f"nasa-toi@{digest}"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")


def checks(oracle: dict) -> dict:
    gap = oracle["gap_gamma1_lr_naive"]
    sens = oracle["sensitivity_nonlinear_resolution"]
    return {
        "control_within_0.01": oracle["control_within_bound"],
        "single_decision": oracle["best"] in oracle["within_threshold"],
        "decision": oracle["decision"],
        "decision_fragile": abs(gap["mean"] - tb.PRACTICAL_THRESHOLD) < gap["se"],
        "sensitivity_agrees": sens["agrees_with_primary"],
        "lockable": oracle["control_within_bound"] and abs(gap["mean"] - tb.PRACTICAL_THRESHOLD) >= gap["se"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--no-fetch", action="store_true", help="reuse the cached CSV instead of downloading")
    p.add_argument("--skip-t1", action="store_true")
    a = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = tb.data_path()

    if a.no_fetch:
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    else:
        digest = tb.fetch(csv_path)
    retrieved = datetime.now(timezone.utc).isoformat()
    pin(tb.spec_path(), digest)
    print(f"[1/4] snapshot {csv_path} sha256={digest} pinned in {tb.spec_path()}")

    t1_out = OUT / "t1.json"
    if not a.skip_t1:
        subprocess.run([sys.executable, str(HERE / "tess_resolution_shift.py"), "--csv", str(csv_path),
                        "--expect-sha256", digest, "--output", str(t1_out)], check=True)
        print(f"[2/4] T1 re-run on the pinned snapshot -> {t1_out}")

    oracle = tb.build_oracle()
    (OUT / "oracle.json").write_text(json.dumps(oracle, indent=2) + "\n")
    print(f"[3/4] simulation oracle -> {OUT / 'oracle.json'}")

    t1 = json.loads(t1_out.read_text()) if t1_out.exists() else None
    summary = {
        "status": "PRELOCK_RUN_SEMI_SYNTHETIC_SIMULATION_NOT_REAL_UNRESOLVED_ACCURACY",
        "snapshot": {"path": str(csv_path.relative_to(REPO)) if csv_path.is_relative_to(REPO) else str(csv_path),
                     "sha256": digest, "recorded_at_utc": retrieved},
        "t1_primary_auc": t1["verdict"]["primary_arm_auc"] if t1 else None,
        "t1_primary_ci95": t1["verdict"]["primary_arm_ci95"] if t1 else None,
        "gap_gamma1_lr_naive": oracle["gap_gamma1_lr_naive"],
        "control_gamma0_mean_gap": oracle["control_gamma0_mean_gap"],
        "sensitivity_nonlinear_resolution": oracle["sensitivity_nonlinear_resolution"],
        "best": oracle["best"], "within_threshold": oracle["within_threshold"],
        "checks": checks(oracle),
        "packages": tb.package_versions(),
        "next": "Record the sha256 and these checks in the bench/PROTOCOL_TESS.md change log, commit the spec pin, "
                "then lock jointly if checks.lockable is true.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"[4/4] summary -> {OUT / 'summary.json'}")
    print(json.dumps(summary["checks"], indent=2))
    return 0 if summary["checks"]["lockable"] else 3


if __name__ == "__main__":
    sys.exit(main())
