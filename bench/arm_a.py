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

Events go through the shared ledger (core/ledger.py, Ledger.append): the same
payload validation, seq/prev_hash assignment and hash format as FORGE's own
agents. An invalid payload is rejected before anything is written. After every
append the run is re-exported to events.jsonl in the episode folder, which is
what bench/report.py reads, so both arms are scored from identical files.

By default each episode has its own ledger database (<episode>/ledger.db), so
an episode folder is self-contained. Pass --ledger to init (for example
results/ledger.db) to write into a shared ledger that the UI and CLI read.

A decision that leaves the plan unchanged is not a ledger event (FINDING needs
an effect and CI); it goes to decisions.jsonl in the episode folder.
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
from datetime import datetime, timedelta, timezone
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT]

from oracle import resolve_runner  # noqa: E402

from core.ledger import Ledger, ValidationError  # noqa: E402

AGENT = "baseline"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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

    def ledger(self, manifest: Optional[dict] = None) -> Ledger:
        m = manifest or self.manifest()
        return Ledger(m.get("ledger_path") or os.path.join(self.path, "ledger.db"))

    def events(self) -> list[dict]:
        m = self.manifest()
        return self.ledger(m).read(m["run_id"])

    def emit(self, type_: str, payload: dict, ai_generated: bool, agent: str = AGENT,
             refs: Optional[dict] = None) -> dict:
        m = self.manifest()
        ledger = self.ledger(m)
        try:
            event = ledger.append(m["run_id"], agent, type_, payload, refs=refs, ai_generated=ai_generated)
        except ValidationError as exc:
            # Nothing was written; tell the agent what to fix.
            raise SystemExit(f"rejected by the ledger: {exc}")
        ledger.export_jsonl(m["run_id"], self.events_path)
        return event


def _git_commit() -> Optional[str]:
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def cmd_init(ep: Episode, a) -> None:
    if os.path.exists(ep.manifest_path):
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
        "ledger_path": os.path.abspath(a.ledger) if a.ledger else None,
        # Budget (bench/PROTOCOL.md section 5). Enforced here so both arms face the same caps.
        "deadline_ts": (datetime.now(timezone.utc) + timedelta(minutes=a.wall_clock_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if a.wall_clock_minutes else None,
        "max_experiments": a.max_experiments,
        "model": a.model,
        "git_commit": _git_commit(),
        "started_at": _now(),
    }
    if ep.ledger(manifest).read(manifest["run_id"]):
        raise SystemExit(f"run {manifest['run_id']} already exists in the ledger; pick another --run-id")
    with open(ep.manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    ep.emit("RUN_CREATED", {"question": a.question, "arm": a.arm, "seed": a.seed, "task_id": a.task_id}, False, agent="system")
    print(f"episode {manifest['run_id']} started at {ep.path}")


def cmd_hypothesis(ep: Episode, a) -> None:
    if not 0 <= a.prior <= 1:
        raise SystemExit("--prior must be between 0 and 1")
    ep.emit("HYPOTHESIS_PROPOSED", {"hid": a.hid, "claim": a.claim, "prediction": a.prediction,
                                    "falsifier": a.falsifier, "prior": a.prior, "label": "AI-generated"}, True,
            refs={"hid": a.hid})
    print(f"recorded hypothesis {a.hid}")


def cmd_predict(ep: Episode, a) -> None:
    if a.sd <= 0:
        raise SystemExit("--sd must be greater than 0: a prediction is a distribution, not a point value")
    metric = ep.manifest()["metric_name"]
    ep.emit("PREDICTION_COMMITTED", {"eid": a.eid, "hid": a.hid, "metric": metric, "mean": a.mean, "sd": a.sd,
                                     "falsifier": a.falsifier}, True, refs={"hid": a.hid, "eid": a.eid})
    print(f"committed prediction for {a.eid}")


def _code_hash(runner_ref: str) -> str:
    """sha256 of the runner's source file, so a result is tied to the exact code that produced it."""
    module = importlib.import_module(runner_ref.partition(":")[0])
    with open(module.__file__, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _numeric_metrics(metrics: dict) -> dict:
    # The event schema allows numbers only; lists such as per-fold scores stay in run_records.jsonl.
    return {k: v for k, v in metrics.items() if isinstance(v, numbers.Real) and not isinstance(v, bool)}


def _check_open(ep: Episode, m: dict) -> None:
    if any(e["type"] == "RUN_COMPLETED" for e in ep.events()):
        raise SystemExit("the episode is closed; nothing more is recorded")
    if _past_deadline(m):
        raise SystemExit(f"budget: wall clock ran out at {m['deadline_ts']}; the episode is over")


def _past_deadline(m: dict) -> bool:
    return bool(m.get("deadline_ts")) and datetime.now(timezone.utc) >= datetime.fromisoformat(
        m["deadline_ts"].replace("Z", "+00:00"))


def cmd_run(ep: Episode, a) -> None:
    m = ep.manifest()
    _check_open(ep, m)
    started = [e for e in ep.events() if e["type"] == "RUN_STARTED"]
    if any(e["payload"].get("eid") == a.eid for e in started):
        raise SystemExit(f"experiment id {a.eid} was already used; pick a new one")
    if m.get("max_experiments") is not None and len(started) >= m["max_experiments"]:
        raise SystemExit(f"budget: all {m['max_experiments']} experiment runs are used; submit your answer")
    params = json.loads(a.params)
    runner = resolve_runner(m["runner"])
    ident = {"eid": a.eid, "hid": a.hid, "code_hash": _code_hash(m["runner"]), "data_ver": m["data_ver"], "seed": m["seed"]}
    committed = any(e["type"] == "PREDICTION_COMMITTED" and e["payload"].get("eid") == a.eid for e in ep.events())
    ep.emit("RUN_STARTED", {**ident, "candidate": a.candidate, "params": params, "prediction_committed": committed},
            False, agent="harness", refs={"hid": a.hid, "eid": a.eid})
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
    ep.emit("RUN_FINISHED", finished, False, agent="harness", refs={"hid": a.hid, "eid": a.eid})
    print(json.dumps({"eid": a.eid, "status": status, "metrics": metrics, "error": record.get("error")}, default=str))


def cmd_decide(ep: Episode, a) -> None:
    # A changed plan counts as a result-driven replan (metric S8).
    if a.changed:
        ep.emit("REPLAN", {"trigger_eid": a.after, "reason": a.decision, "reopened": a.reopen or []}, True,
                refs={"eid": a.after})
    else:
        with open(os.path.join(ep.path, "decisions.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "after": a.after, "decision": a.decision, "plan_changed": False}) + "\n")
    print("recorded decision")


def cmd_answer(ep: Episode, a) -> None:
    if any(e["type"] == "RUN_COMPLETED" for e in ep.events()):
        raise SystemExit("final answer already submitted")
    if _past_deadline(ep.manifest()):
        raise SystemExit("budget: wall clock ran out; answers after the deadline are not accepted")
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
    s.add_argument("--ledger", help="shared ledger database (default: <episode>/ledger.db)")
    s.add_argument("--wall-clock-minutes", type=float, help="episode deadline, minutes from init")
    s.add_argument("--max-experiments", type=int, help="maximum experiment runs")

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

    s = sub.add_parser("close", help="harness only: end an episode that has no final answer")
    s.add_argument("--status", required=True, choices=["budget_exhausted", "aborted"])
    s.add_argument("--summary", default="")
    return p


def cmd_close(ep: Episode, a) -> None:
    if any(e["type"] == "RUN_COMPLETED" for e in ep.events()):
        print("episode already completed")
        return
    m = ep.manifest()
    ep.emit("RUN_COMPLETED", {"status": a.status, "summary": a.summary or "no final answer submitted"}, False, agent="harness")
    # report.py ends the timed window at RUN_COMPLETED; keep the cutoff in the manifest too.
    m["budget_end_ts"] = m.get("deadline_ts") or _now()
    with open(ep.manifest_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    print(f"episode closed: {a.status}")


COMMANDS = {"close": cmd_close, "init": cmd_init, "hypothesis": cmd_hypothesis, "predict": cmd_predict, "run": cmd_run,
            "decide": cmd_decide, "answer": cmd_answer}


def main(argv: Optional[list[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    if not a.episode:
        raise SystemExit("set --episode or FORGE_EPISODE_DIR")
    COMMANDS[a.cmd](Episode(a.episode), a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
