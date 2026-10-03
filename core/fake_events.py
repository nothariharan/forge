"""Write a realistic fake run so the UI and CLI can be built before the agents exist.

    python -m core.fake_events --run-id demo --delay 0.5

All data is made up (question, numbers, citations). It is a fixture, not a result.
"""
from __future__ import annotations

import argparse
import time

from core.ledger import DEFAULT_PATH, Ledger

# Shaped like the science lane's provisional candidate (docs/coordination/SCIENCE_CONTRACT.md):
# OpenML task 7592 (adult), accuracy. Every number below is invented.
QUESTION = ("Fixture only: on OpenML task 7592 (adult), does adding missingness indicators to "
            "median/mode imputation change logistic-regression accuracy?")
DATA_VER = "openml-task-7592/adult-v2"


def _run_cycle(eid: str, hid: str, seed: int, candidate: dict, metrics: dict,
               effect: float, ci: list, verdict: str, agreement: float):
    """RUN_STARTED -> RUN_FINISHED -> FINDING -> CONSENSUS for one experiment."""
    run = {"eid": eid, "hid": hid, "code_hash": "9f2c1e7", "data_ver": DATA_VER, "seed": seed, "candidate": candidate}
    refs = {"eid": eid, "hid": hid}
    return [
        ("experimenter", "RUN_STARTED", run, refs),
        ("experimenter", "RUN_FINISHED", {**run, "status": "ok", "metrics": metrics}, refs),
        ("analyst", "FINDING", {"eid": eid, "effect": effect, "ci": ci, "verdict": verdict}, refs),
        ("referee", "CONSENSUS", {"eid": eid, "agreement": agreement, "accepted": True}, refs),
    ]


def _claim(text: str, ref: str, quote: str):
    return ("librarian", "EVIDENCE_ADDED", {"claims": [{"text": text, "ref": ref, "quote_span": quote}]}, {})


def _hypothesis(hid: str, claim: str, prediction: str, falsifier: str, prior: float):
    payload = {"hid": hid, "claim": claim, "prediction": prediction, "falsifier": falsifier, "prior": prior}
    return ("hypothesizer", "HYPOTHESIS_PROPOSED", payload, {"hid": hid})


def _novelty(hid: str, label: str, prior_art: list):
    return ("referee", "NOVELTY_VERDICT", {"hid": hid, "label": label, "prior_art": prior_art}, {"hid": hid})


def _prediction(hid: str, eid: str, metric: str, mean: float, sd: float):
    payload = {"hid": hid, "eid": eid, "metric": metric, "mean": mean, "sd": sd}
    return ("hypothesizer", "PREDICTION_COMMITTED", payload, {"hid": hid, "eid": eid})


# (agent, type, payload, refs) in emission order.
SCRIPT = [
    ("system", "RUN_CREATED", {"question": QUESTION, "budget": 100.0, "mode": "fake"}, {}),

    _claim("Missingness indicators can help when the fact that a value is missing is itself informative.",
           "arXiv:0000.00001", "adding an indicator lets the model use informative missingness"),
    _claim("With simple imputation, linear models often lose little accuracy when few values are missing.",
           "arXiv:0000.00002", "mean and mode imputation were competitive when under ten percent of cells were missing"),
    _claim("Encoding a missing category as its own level is a common alternative to imputing it.",
           "10.0000/fake.2024.0042", "treating missing as a separate category matched imputation plus indicators"),

    _hypothesis("H1", "Adding missingness indicators to median/mode imputation raises accuracy on adult.",
                "Accuracy gain of about 0.004.", "Gain below 0.001 with a CI that includes 0.", 0.6),
    _hypothesis("H2", "The gain from indicators is concentrated in rows that have a missing value.",
                "Gain on rows with a missing value is at least 0.01 larger than on complete rows.",
                "Gain is the same on both groups.", 0.45),
    _hypothesis("H3", "Indicators help when missingness is informative about the target.",
                "Accuracy rises with indicators on data with informative missingness.",
                "No gain on any such dataset.", 0.8),
    _hypothesis("H4", "Encoding a missing category as its own level matches mode imputation plus indicators.",
                "Accuracy gap below 0.001.", "A gap above 0.003.", 0.35),

    _novelty("H1", "NOVEL", []),
    _novelty("H2", "NOVEL", []),
    _novelty("H3", "KNOWN", ["arXiv:0000.00001"]),
    _novelty("H4", "NOVEL", ["10.0000/fake.2024.0042"]),

    _prediction("H1", "E1", "accuracy_gain", 0.004, 0.001),
    _prediction("H2", "E2", "accuracy_gain_missing_minus_complete_rows", 0.01, 0.006),
    _prediction("H4", "E3", "accuracy_gap", 0.0, 0.001),

    ("planner", "EXPERIMENT_SELECTED", {
        "candidates": [
            {"eid": "E1", "hid": "H1", "design": "Median/mode imputation with vs without missingness indicators, 10-fold CV", "est_cost": 12.0, "eig": 0.41},
            {"eid": "E2", "hid": "H2", "design": "Same comparison, scored separately on rows with and without missing values", "est_cost": 30.0, "eig": 0.52},
        ],
        "chosen": "E1", "budget_left": 88.0,
    }, {"eid": "E1", "hid": "H1"}),

    *_run_cycle("E1", "H1", seed=0, candidate={"imputation": "median_mode", "missing_indicators": True},
                metrics={"accuracy": 0.8516, "accuracy_baseline": 0.8514, "accuracy_gain": 0.0002},
                effect=0.0002, ci=[-0.0011, 0.0015], verdict="INCONCLUSIVE", agreement=0.83),

    ("analyst", "SURPRISE", {"eid": "E1", "hid": "H1", "observed": 0.0002, "surprise_score": 3.8, "threshold": 2.0},
     {"eid": "E1", "hid": "H1"}),
    ("planner", "REPLAN", {"reason": "E1 gain is far below the committed prediction for H1; the encoding of missing categories (H4) may explain it.",
                           "trigger_eid": "E1", "reopened": ["H4"]}, {"parent": "E1", "hid": "H4"}),
    ("planner", "EXPERIMENT_SELECTED", {
        "candidates": [
            {"eid": "E3", "hid": "H4", "design": "Missing category as its own level vs mode imputation plus indicators, 10-fold CV", "est_cost": 14.0, "eig": 0.63},
            {"eid": "E2", "hid": "H2", "design": "Same comparison, scored separately on rows with and without missing values", "est_cost": 30.0, "eig": 0.38},
        ],
        "chosen": "E3", "budget_left": 74.0,
    }, {"eid": "E3", "hid": "H4", "parent": "E1"}),
    ("safety", "POLICY_DENIED", {"policy_id": "P1", "target_agent": "librarian",
                                 "reason": "Bad citation: arXiv:0000.99999 does not resolve, so the claim was rejected."}, {}),

    *_run_cycle("E3", "H4", seed=1, candidate={"imputation": "missing_as_category", "missing_indicators": False},
                metrics={"accuracy": 0.8519, "accuracy_baseline": 0.8516, "accuracy_gap": 0.0003},
                effect=0.0003, ci=[-0.0006, 0.0012], verdict="SUPPORTS", agreement=0.92),

    ("safety", "GATE_OPENED", {"gate_id": "G1", "action": "Publish the E3 finding to the shared report",
                               "risk": "medium", "status": "pending"}, {"gate_id": "G1", "eid": "E3"}),
    ("system", "GATE_RESOLVED", {"gate_id": "G1", "action": "Publish the E3 finding to the shared report",
                                 "risk": "medium", "status": "approved"}, {"gate_id": "G1", "eid": "E3"}),

    ("system", "RUN_COMPLETED", {"status": "completed", "summary": "Fixture run: 2 experiments, 1 replan, 1 gate."}, {}),
]


def emit_fake_run(ledger: Ledger, run_id: str = "demo", delay: float = 0.0, verbose: bool = False) -> list[dict]:
    events = []
    for agent, type, payload, refs in SCRIPT:
        event = ledger.append(run_id, agent, type, payload, refs=refs, ai_generated=agent != "system")
        events.append(event)
        if verbose:
            print(f"{event['seq']:>3}  {agent:<13} {type}", flush=True)
        time.sleep(delay)
    return events


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Write a fake FORGE run to the ledger.")
    p.add_argument("--run-id", default="demo")
    p.add_argument("--delay", type=float, default=0.5, help="seconds between events")
    p.add_argument("--db", default=DEFAULT_PATH, help="ledger path")
    args = p.parse_args(argv)
    events = emit_fake_run(Ledger(args.db), args.run_id, args.delay, verbose=True)
    print(f"wrote {len(events)} events to run {args.run_id!r} in {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
