"""Tools the arm A (single-agent baseline) agent calls during an episode.

The baseline agent gets plain commands instead of FORGE's agents and
policies. Each command appends ledger-format events to the episode folder so
bench/report.py scores arm A and arm B with the same code
(bench/PROTOCOL.md section 11). Experiment start/finish events are written by
this harness around the runner call, not by the agent, so the record does not
depend on the agent remembering to log.

Arm A gets no policy gates: nothing here blocks an experiment without a
committed prediction. Violations are recorded and counted (metric S7), the
same way they would be if FORGE's gate failed.

The episode folder comes from --episode or $FORGE_EPISODE_DIR.

    python bench/arm_a.py init --arm A --seed 1 --question "..." --metric roc_auc \
        --runner tools.openml_run:run --task-id 7592 --data-ver openml:1590@2
    python bench/arm_a.py hypothesis --hid H1 --claim "..." --prediction "..." --falsifier "..." --prior 0.5
    python bench/arm_a.py predict --eid E1 --hid H1 --mean 0.905 --sd 0.004 --falsifier "..."
    python bench/arm_a.py run --eid E1 --hid H1 --candidate lr_mode --params '{"model": "lr"}'
    python bench/arm_a.py decide --after E1 --decision "..." [--changed --reopen H1]
    python bench/arm_a.py answer --candidate lr_mode --report final_report.md

Payloads follow the per-event schemas in schemas/*.json (core/schemas.py), so
arm A events are accepted by the shared ledger. A decision that leaves the
plan unchanged is not a ledger event (FINDING needs an effect and CI); it goes
to decisions.jsonl in the episode folder.

Hashing follows the design doc: hash = sha256(prev_hash + canonical_json(event
without hash)). Swap in core/ledger.py once it is merged so both arms share
one implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import numbers
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oracle import resolve_runner  # noqa: E402

SCHEMA_VERSION = "1.0"
AGENT = "baseline"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Episode:
    def __init__(self, path: str):
        self.path = path
        self.events_path = os.path.join(path, "events.jsonl")
        self.manifest_path = os.path.join(path, "manifest.json")

    def manifest(self) -> dict:
        if not os.path.exists(self.manifest_path):
            raise SystemExit(f"no episode at {self.path}; run 'init' first")
        with open(self.manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def events(self) -> list[dict]:
        if not os.path.exists(self.events_path):
            return []
        with open(self.events_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def emit(self, type_: str, payload: dict, ai_generated: bool, agent: str = AGENT) -> dict:
        events = self.events()
        prev = events[-1]["hash"] if events else "GENESIS"
        event = {
            "schema_version": SCHEMA_VERSION,
            "seq": len(events) + 1,
            "ts": _now(),
            "run_id": self.manifest()["run_id"],
            "agent": agent,
            "type": type_,
            "payload": payload,
            "ai_generated": ai_generated,
            "prev_hash": prev,
        }
        event["hash"] = hashlib.sha256((prev + _canonical(event)).encode()).hexdigest()
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event


def _git_commit() -> Optional[str]:
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def cmd_init(ep: Episode, a) -> None:
    if os.path.exists(ep.events_path):
        raise SystemExit(f"episode already started at {ep.path}")
    os.makedirs(ep.path, exist_ok=True)
    manifest = {
        "run_id": a.run_id or f"{a.arm}-seed{a.seed}-{int(time.time())}",
        "arm": a.arm,
        "seed": a.seed,
        "question": a.question,
        "task_id": a.task_id,
        "metric_name": a.metric,
        "runner": a.runner,
        "data_ver": a.data_ver,
        "model": a.model,
        "git_commit": _git_commit(),
        "started_at": _now(),
    }
    with open(ep.manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    ep.emit("RUN_CREATED", {"question": a.question, "arm": a.arm, "seed": a.seed, "task_id": a.task_id}, False, agent="system")
    print(f"episode {manifest['run_id']} started at {ep.path}")


def cmd_hypothesis(ep: Episode, a) -> None:
    if not 0 <= a.prior <= 1:
        raise SystemExit("--prior must be between 0 and 1")
    ep.emit("HYPOTHESIS_PROPOSED", {"hid": a.hid, "claim": a.claim, "prediction": a.prediction,
                                    "falsifier": a.falsifier, "prior": a.prior, "label": "AI-generated"}, True)
    print(f"recorded hypothesis {a.hid}")


def cmd_predict(ep: Episode, a) -> None:
    if a.sd <= 0:
        raise SystemExit("--sd must be greater than 0: a prediction is a distribution, not a point value")
    metric = ep.manifest()["metric_name"]
    ep.emit("PREDICTION_COMMITTED", {"eid": a.eid, "hid": a.hid, "metric": metric, "mean": a.mean, "sd": a.sd,
                                     "falsifier": a.falsifier}, True)
    print(f"committed prediction for {a.eid}")


def _code_hash(runner_ref: str) -> str:
    """sha256 of the runner's source file, so a result is tied to the exact code that produced it."""
    module = importlib.import_module(runner_ref.partition(":")[0])
    with open(module.__file__, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _numeric_metrics(metrics: dict) -> dict:
    # The event schema allows numbers only; lists such as per-fold scores stay in run_records.jsonl.
    return {k: v for k, v in metrics.items() if isinstance(v, numbers.Real) and not isinstance(v, bool)}


def cmd_run(ep: Episode, a) -> None:
    m = ep.manifest()
    if any(e["type"] == "RUN_STARTED" and e["payload"].get("eid") == a.eid for e in ep.events()):
        raise SystemExit(f"experiment id {a.eid} was already used; pick a new one")
    params = json.loads(a.params)
    runner = resolve_runner(m["runner"])
    ident = {"eid": a.eid, "hid": a.hid, "code_hash": _code_hash(m["runner"]), "data_ver": m["data_ver"], "seed": m["seed"]}
    committed = any(e["type"] == "PREDICTION_COMMITTED" and e["payload"].get("eid") == a.eid for e in ep.events())
    ep.emit("RUN_STARTED", {**ident, "candidate": a.candidate, "params": params, "prediction_committed": committed},
            False, agent="harness")
    t0 = time.monotonic()
    record = {**ident, "candidate": a.candidate, "params": params}
    try:
        result = runner(m["task_id"], params, m["seed"])
        metrics = (result or {}).get("metrics", {})
        status = "ok" if metrics.get(m["metric_name"]) is not None else "missing_metric"
        record.update(status=status, metrics=metrics, raw=result)
    except Exception as exc:
        status, metrics = "error", {}
        record.update(status=status, metrics={}, error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(limit=5))
    record["wall_seconds"] = round(time.monotonic() - t0, 3)
    with open(os.path.join(ep.path, "run_records.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    finished = {**ident, "status": status, "metrics": _numeric_metrics(metrics), "wall_seconds": record["wall_seconds"]}
    if record.get("error"):
        finished["error"] = record["error"]
    ep.emit("RUN_FINISHED", finished, False, agent="harness")
    print(json.dumps({"eid": a.eid, "status": status, "metrics": metrics, "error": record.get("error")}, default=str))


def cmd_decide(ep: Episode, a) -> None:
    # A changed plan counts as a result-driven replan (metric S8).
    if a.changed:
        ep.emit("REPLAN", {"trigger_eid": a.after, "reason": a.decision, "reopened": a.reopen or []}, True)
    else:
        with open(os.path.join(ep.path, "decisions.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "after": a.after, "decision": a.decision, "plan_changed": False}) + "\n")
    print("recorded decision")


def cmd_answer(ep: Episode, a) -> None:
    if any(e["type"] == "RUN_COMPLETED" for e in ep.events()):
        raise SystemExit("final answer already submitted")
    with open(os.path.join(ep.path, "answer.json"), "w", encoding="utf-8") as f:
        json.dump({"candidate": a.candidate, "submitted_at": _now()}, f, indent=2)
    if a.report:
        dest = os.path.join(ep.path, "final_report.md")
        if os.path.abspath(a.report) != os.path.abspath(dest):
            shutil.copyfile(a.report, dest)
    ep.emit("RUN_COMPLETED", {"status": "completed", "candidate": a.candidate}, True)
    print(f"final answer recorded: {a.candidate}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Arm A baseline episode tools.")
    p.add_argument("--episode", default=os.environ.get("FORGE_EPISODE_DIR"), help="episode folder (default $FORGE_EPISODE_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.add_argument("--arm", default="A")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--question", required=True)
    s.add_argument("--metric", required=True)
    s.add_argument("--runner", required=True, help="module:function, same runner as FORGE")
    s.add_argument("--task-id", required=True)
    s.add_argument("--data-ver", required=True, help="dataset identifier and version, e.g. openml:1590@2")
    s.add_argument("--model", help="model ID used by the agent")
    s.add_argument("--run-id")

    s = sub.add_parser("hypothesis")
    s.add_argument("--hid", required=True)
    s.add_argument("--claim", required=True)
    s.add_argument("--prediction", required=True, help="what you expect to observe if the claim is true")
    s.add_argument("--falsifier", required=True, help="the result that would show the claim is wrong")
    s.add_argument("--prior", type=float, required=True, help="your probability, 0 to 1, that the claim is true")

    s = sub.add_parser("predict")
    s.add_argument("--eid", required=True)
    s.add_argument("--hid", required=True)
    s.add_argument("--mean", type=float, required=True, help="predicted value of the episode metric")
    s.add_argument("--sd", type=float, required=True, help="uncertainty of the prediction (standard deviation, > 0)")
    s.add_argument("--falsifier", required=True)

    s = sub.add_parser("run")
    s.add_argument("--eid", required=True)
    s.add_argument("--hid", required=True)
    s.add_argument("--candidate", required=True)
    s.add_argument("--params", default="{}", help="JSON params passed to the runner")

    s = sub.add_parser("decide")
    s.add_argument("--after", required=True, help="experiment id whose result informed this decision")
    s.add_argument("--decision", required=True)
    s.add_argument("--changed", action="store_true", help="the result changed the plan")
    s.add_argument("--reopen", nargs="*", help="hypothesis or experiment ids the change reopens")

    s = sub.add_parser("answer")
    s.add_argument("--candidate", required=True)
    s.add_argument("--report", help="path to the final report markdown")
    return p


COMMANDS = {"init": cmd_init, "hypothesis": cmd_hypothesis, "predict": cmd_predict, "run": cmd_run,
            "decide": cmd_decide, "answer": cmd_answer}


def main(argv: Optional[list[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    if not a.episode:
        raise SystemExit("set --episode or FORGE_EPISODE_DIR")
    COMMANDS[a.cmd](Episode(a.episode), a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
