"""Write the astronomy-themed DEMO run the lab UI replays.

    .venv/bin/python ui/fixtures/make_exo_demo.py

Every event goes through the real Ledger.append (so it is schema-valid and
hash-chained) and is then exported to ui/fixtures/exo-demo.jsonl.

This is a fixture, not a result. The science question is NOT locked. All
numbers, ids and citations are invented placeholders and every payload carries
"demo": true. Catalog statuses are kept distinct (CANDIDATE is not CONFIRMED),
and no value here is a planet precision or prevalence.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.ledger import Ledger  # noqa: E402

RUN_ID = "exo-demo"
OUT = Path(__file__).with_name("exo-demo.jsonl")
DATA_VER = "demo:tess-toi-snapshot"
D = {"demo": True}

QUESTION = ("Demo only (question not locked): does triage accuracy measured on resolved TESS "
            "objects of interest overstate accuracy on the unresolved planet candidates "
            "the model is actually used to triage?")

COHORTS = {
    "resolved": ["CONFIRMED", "FALSE POSITIVE"],
    "unresolved": ["CANDIDATE"],
    "excluded": ["UNKNOWN"],
    "note": "CANDIDATE is not a confirmed planet. Cohort sizes are not shown in the demo.",
}


def claim(text, ref, quote):
    return ("librarian", "EVIDENCE_ADDED", {"claims": [{"text": text, "ref": ref, "quote_span": quote}], **D}, {})


def run_pair(eid, hid, seed, candidate, metrics):
    run = {"eid": eid, "hid": hid, "code_hash": "demo000", "data_ver": DATA_VER, "seed": seed,
           "candidate": candidate, **D}
    refs = {"eid": eid, "hid": hid}
    return [("experimenter", "RUN_STARTED", run, refs),
            ("experimenter", "RUN_FINISHED", {**run, "status": "ok", "metrics": metrics}, refs)]


EVENTS = [
    ("system", "RUN_CREATED", {"question": QUESTION, "budget": 10.0, "mode": "demo",
                               "dataset": "NASA Exoplanet Archive, TESS TOI table (demo snapshot)",
                               "cohorts": COHORTS, **D}, {}),
    claim("Catalog vetting models are usually scored on objects whose status is already resolved.",
          "arXiv:0000.10001", "evaluated on dispositioned objects only"),
    claim("Resolved and unresolved candidates can differ in signal-to-noise and orbital period.",
          "arXiv:0000.10002", "the unresolved sample is fainter on average"),
    claim("Importance weighting can estimate performance under covariate shift.",
          "10.0000/demo.2025.0003", "reweighting by the density ratio recovers the target risk"),
    ("hypothesizer", "HYPOTHESIS_PROPOSED",
     {"hid": "H1", "claim": "Accuracy on resolved TOIs overstates accuracy on unresolved candidates.",
      "prediction": "Shift-weighted AUC is lower than resolved-cohort AUC.",
      "falsifier": "AUC gap below 0.01 with an interval that includes 0.", "prior": 0.6, **D}, {"hid": "H1"}),
    ("hypothesizer", "HYPOTHESIS_PROPOSED",
     {"hid": "H2", "claim": "Any gap is explained by the signal-to-noise distribution alone.",
      "prediction": "The gap vanishes after matching on SNR.",
      "falsifier": "Gap persists after SNR matching.", "prior": 0.4, **D}, {"hid": "H2"}),
    ("referee", "NOVELTY_VERDICT", {"hid": "H1", "label": "UNCERTAIN", "prior_art": ["arXiv:0000.10001"], **D}, {"hid": "H1"}),
    ("referee", "NOVELTY_VERDICT", {"hid": "H2", "label": "UNCERTAIN", "prior_art": [], **D}, {"hid": "H2"}),
    ("hypothesizer", "PREDICTION_COMMITTED",
     {"hid": "H1", "eid": "E1", "metric": "auc_gap", "mean": 0.04, "sd": 0.02, **D}, {"hid": "H1", "eid": "E1"}),
    ("planner", "EXPERIMENT_SELECTED",
     {"candidates": [
         {"eid": "E1", "hid": "H1", "design": "Cheap shift check: importance-weighted AUC, resolved vs shifted", "est_cost": 1.5, "eig": 0.38},
         {"eid": "E2", "hid": "H1", "design": "Semi-synthetic oracle with known truth", "est_cost": 6.0, "eig": 0.55}],
      "chosen": "E1", "budget_left": 8.5,
      "rationale": "E1 has higher expected information per unit cost (0.25 vs 0.09).", **D},
     {"hid": "H1", "eid": "E1"}),
    ("safety", "GATE_OPENED",
     {"gate_id": "G1", "action": "Run E1 (shift check)", "risk": "low", "status": "pending", "policy": "P6", **D},
     {"eid": "E1", "gate_id": "G1"}),
    ("system", "GATE_RESOLVED",
     {"gate_id": "G1", "action": "Run E1 (shift check)", "risk": "low", "status": "approved", "policy": "P6", **D},
     {"eid": "E1", "gate_id": "G1"}),
    *run_pair("E1", "H1", 0, {"weighting": "importance", "model": "gradient_boosting"},
              {"auc_resolved": 0.91, "auc_shifted": 0.83, "auc_gap": 0.08}),
    ("analyst", "FINDING", {"eid": "E1", "effect": 0.08, "ci": [0.05, 0.11], "verdict": "SUPPORTS", **D}, {"eid": "E1", "hid": "H1"}),
    ("analyst", "SURPRISE", {"eid": "E1", "hid": "H1", "observed": 0.08, "surprise_score": 2.0, "threshold": 1.5, **D}, {"eid": "E1", "hid": "H1"}),
    ("planner", "REPLAN",
     {"reason": "E1 gap is twice the committed prediction; test whether SNR alone explains it (H2).",
      "trigger_eid": "E1", "reopened": ["H2"], **D}, {"hid": "H2", "parent": "E1"}),
    ("safety", "POLICY_DENIED",
     {"policy_id": "P1", "target_agent": "librarian",
      "reason": "Bad citation: arXiv:0000.19999 does not resolve, so the claim was rejected.", **D}, {}),
    ("hypothesizer", "PREDICTION_COMMITTED",
     {"hid": "H2", "eid": "E3", "metric": "auc_gap_snr_matched", "mean": 0.0, "sd": 0.02, **D}, {"hid": "H2", "eid": "E3"}),
    ("planner", "EXPERIMENT_SELECTED",
     {"candidates": [
         {"eid": "E3", "hid": "H2", "design": "Repeat E1 after matching cohorts on SNR", "est_cost": 2.0, "eig": 0.41},
         {"eid": "E4", "hid": "H2", "design": "Stratify by SNR decile, no matching", "est_cost": 2.5, "eig": 0.30}],
      "chosen": "E3", "budget_left": 6.5,
      "rationale": "E3 isolates SNR directly at lower cost.", **D},
     {"hid": "H2", "eid": "E3", "parent": "E1"}),
    ("safety", "GATE_OPENED",
     {"gate_id": "G2", "action": "Run E3 (SNR-matched shift check)", "risk": "low", "status": "pending", "policy": "P6", **D},
     {"eid": "E3", "gate_id": "G2"}),
    ("system", "GATE_RESOLVED",
     {"gate_id": "G2", "action": "Run E3 (SNR-matched shift check)", "risk": "low", "status": "approved", "policy": "P6", **D},
     {"eid": "E3", "gate_id": "G2"}),
    *run_pair("E3", "H2", 0, {"weighting": "importance", "matching": "snr", "model": "gradient_boosting"},
              {"auc_resolved": 0.90, "auc_shifted": 0.87, "auc_gap_snr_matched": 0.03}),
    ("analyst", "FINDING", {"eid": "E3", "effect": 0.03, "ci": [0.0, 0.06], "verdict": "INCONCLUSIVE", **D}, {"eid": "E3", "hid": "H2"}),
    ("referee", "CONSENSUS", {"eid": "E3", "agreement": 0.8, "accepted": True, **D}, {"eid": "E3", "hid": "H2"}),
    ("system", "RUN_COMPLETED",
     {"status": "completed",
      "summary": "Demo run: 2 experiments, 1 replan, 2 approvals, 1 policy denial. Next: semi-synthetic oracle (E2).",
      **D}, {}),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(os.path.join(tmp, "demo.db"))
        for agent, type_, payload, refs in EVENTS:
            ledger.append(RUN_ID, agent, type_, payload, refs=refs or None,
                          ai_generated=agent not in ("system",))
            time.sleep(0.6)  # spread timestamps so the replay clock moves
        ok, bad = ledger.verify(RUN_ID)
        assert ok, f"chain broken at {bad}"
        if OUT.exists():
            OUT.unlink()
        ledger.export_jsonl(RUN_ID, str(OUT))
    print(f"wrote {len(EVENTS)} events to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
