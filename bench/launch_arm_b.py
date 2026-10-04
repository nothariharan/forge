"""Launch one arm B (FORGE) episode under Omnigent, matched to arm A.

FORGE's director writes its events to the shared ledger through
tools/forge_emit.py, using the run id given in its task message. This launcher
owns everything around that, the same way bench/launch_arm_a.py does for arm A,
so both arms are timed, cut off and closed by identical code:

1. Build the task message from the same spec, with the research question,
   task, budget and research rules copied verbatim from the arm A prompt
   (bench/baseline_prompt.md), so both arms receive the same information.
2. Write the episode manifest and record RUN_CREATED (opens the timed window).
3. Run FORGE headless with FORGE_LEDGER_DB pointing at the episode ledger,
   stdin closed and a hard timeout at the wall-clock budget.
4. If FORGE did not record RUN_COMPLETED, close the episode as
   budget_exhausted or aborted. Its final answer is the "candidate" field of
   RUN_COMPLETED, saved as answer.json for scoring.
5. Export the run to events.jsonl, which bench/report.py reads.

Default command (headless form confirmed by the orchestration lane):

    omni run omnigent/forge --no-session -p "<task message>" </dev/null

Usage:
    python bench/launch_arm_b.py --spec spec.json --seed 1 --episode results/bench/<id>/B/seed-1 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BENCH_DIR)
sys.path[:0] = [BENCH_DIR, REPO_ROOT]

import launch_arm_a as shared  # noqa: E402

from core.ledger import Ledger  # noqa: E402

DEFAULT_AGENT_CMD = "omni run omnigent/forge --no-session -p {prompt}"
SHARED_SECTIONS = ("### Research question", "### Task and metric", "### Budget", "### Research rules")


def _section(prompt: str, heading: str) -> str:
    start = prompt.index(heading)
    nxt = prompt.find("\n### ", start + len(heading))
    return prompt[start:nxt if nxt != -1 else len(prompt)].strip()


def run_section(spec: dict, seed: Optional[int]) -> str:
    """How FORGE runs one experiment: the same runner arm A calls through `bench/arm_a.py run`."""
    if not spec.get("runner_command"):
        return ""
    cmd = spec["runner_command"].replace("{SEED}", str(seed) if seed is not None else "<seed>")
    return (
        "### Running an experiment\n\n"
        f"Each experiment is one run of this command (the experimenter runs it behind the P6 gate); the seed is fixed:\n\n"
        f"    {cmd}\n\n"
        "It prints JSON; its `metrics` object holds the metric. Label each experiment with the candidate id "
        "`<model>_<estimator>_g<gamma>` and put it in the RUN_STARTED and RUN_FINISHED payloads as \"candidate\".\n\n"
    )


def loop_section(spec: dict) -> str:
    """Benchmark mode: run the whole loop; without a literature tool, skip the evidence steps instead of
    blocking on an empty evidence packet (the schema needs at least one sourced claim)."""
    text = ("### How to run this episode\n\n"
            "Run the full loop (planner, safety, experimenter, analyst, repeated) until the question is answered "
            "or the budget runs out, then record RUN_COMPLETED. Nobody will reply during the episode.\n")
    if str(spec.get("literature_tools", "")).lower().startswith("no literature tool"):
        text += ("No literature tool is provided in this episode, so skip the librarian and the referee: record no "
                 "EVIDENCE_ADDED or NOVELTY_VERDICT, give the hypothesizer the research question and task text "
                 "above as its input, and tell the planner the novelty check was not run.\n")
    return text + "\n"


def task_message(spec: dict, run_id: str, seed: Optional[int] = None) -> str:
    """FORGE's task: the arm A prompt's shared sections, verbatim, plus how to run an experiment and record the answer."""
    filled = shared.fill_prompt(spec)
    body = "\n\n".join(_section(filled, h) for h in SHARED_SECTIONS)
    return (
        f"Run id: {run_id}\n\n"
        "Investigate the research question below with the FORGE team and record every handoff in the ledger.\n\n"
        f"{body}\n\n"
        f"{loop_section(spec)}"
        f"{run_section(spec, seed)}"
        "### Final answer\n\n"
        "End the run by recording RUN_COMPLETED with "
        '{"status": "completed", "summary": "<one paragraph>", "candidate": "<id of the candidate you recommend>"}. '
        "Only the candidate recorded there is scored.\n"
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_deadline(manifest: dict) -> bool:
    return datetime.now(timezone.utc) >= datetime.fromisoformat(manifest["deadline_ts"].replace("Z", "+00:00"))


def launch(spec: dict, seed: int, episode_dir: str, run_id: Optional[str] = None, model: Optional[str] = None,
           agent_cmd: str = DEFAULT_AGENT_CMD, dry_run: bool = False) -> dict:
    run_id = run_id or f"B-seed{seed}-{int(time.time())}"
    prompt = task_message(spec, run_id, seed)  # fails before anything is created if a placeholder is missing
    if os.path.exists(os.path.join(episode_dir, "manifest.json")):
        raise SystemExit(f"episode already started at {episode_dir}")
    os.makedirs(episode_dir, exist_ok=True)
    ledger_path = os.path.join(os.path.abspath(episode_dir), "ledger.db")
    ledger = Ledger(ledger_path)
    if ledger.read(run_id):
        raise SystemExit(f"run {run_id} already exists in the ledger; pick another --run-id")

    manifest = {
        "run_id": run_id, "arm": "B", "seed": seed, "question": spec["question"], "task_id": spec["task_id"],
        "metric_name": spec["metric"], "runner": spec["runner"], "data_ver": spec["data_ver"], "model": model,
        "ledger_path": ledger_path, "started_at": _now(),
        "deadline_ts": (datetime.now(timezone.utc) + timedelta(minutes=float(spec["wall_clock_minutes"])))
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "max_experiments": spec["max_experiments"],
    }
    with open(os.path.join(episode_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(episode_dir, "prompt.md"), "w", encoding="utf-8") as f:
        f.write(prompt)
    # The harness opens the timed window, as it does for arm A; a RUN_CREATED from the director comes later.
    ledger.append(run_id, "system", "RUN_CREATED", {"question": spec["question"], "mode": "benchmark"})

    prompt_file = os.path.join(os.path.abspath(episode_dir), "prompt.md")
    cmd, shown = shared.build_cmd(agent_cmd, {"{prompt}": prompt, "{prompt_file}": prompt_file}, prompt)
    record = {"run_id": run_id, "seed": seed, "command": shown, "dry_run": dry_run}
    if dry_run:
        record["note"] = "dry run: episode initialised; FORGE not started"
    else:
        env = {**os.environ, "FORGE_LEDGER_DB": ledger_path, "FORGE_EPISODE_DIR": os.path.abspath(episode_dir),
               "FORGE_GATE_MODE": "auto",  # no human in the matched benchmark; logged as harness approval
               **shared.model_env(model)}
        record.update(shared.run_agent(cmd, env, float(spec["wall_clock_minutes"]) * 60 + shared.GRACE_SECONDS,
                                       episode_dir))
        if not any(e["type"] == "RUN_COMPLETED" for e in ledger.read(run_id)):
            status = "budget_exhausted" if record["timed_out"] or _past_deadline(manifest) else "aborted"
            ledger.append(run_id, "harness", "RUN_COMPLETED",
                          {"status": status, "summary": f"FORGE ended without RUN_COMPLETED (returncode={record['returncode']})"})
            manifest["budget_end_ts"] = manifest["deadline_ts"] if status == "budget_exhausted" else _now()
            with open(os.path.join(episode_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        completed = next(e for e in ledger.read(run_id) if e["type"] == "RUN_COMPLETED")
        record["outcome"] = completed["payload"].get("status")
        if completed["payload"].get("candidate") is not None:
            with open(os.path.join(episode_dir, "answer.json"), "w", encoding="utf-8") as f:
                json.dump({"candidate": completed["payload"]["candidate"], "submitted_at": completed["ts"]}, f, indent=2)

    ledger.export_jsonl(run_id, os.path.join(episode_dir, "events.jsonl"))
    with open(os.path.join(episode_dir, "launcher.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return record


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Launch one arm B (FORGE) episode.")
    p.add_argument("--spec", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--episode", required=True, help="episode folder, e.g. results/bench/<id>/B/seed-1")
    p.add_argument("--run-id")
    p.add_argument("--model", help="model ID, recorded in the manifest (must match arm A)")
    p.add_argument("--agent-cmd", default=DEFAULT_AGENT_CMD, help="{prompt} and {prompt_file} are substituted")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    print(json.dumps(launch(shared.load_spec(a.spec), a.seed, a.episode, a.run_id, a.model, a.agent_cmd, a.dry_run),
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
