# Omnigent arm A demo run (stub runner)

Proof that the arm A baseline runs end to end under Omnigent: the launcher starts a one-agent Omnigent config with `omni run`, the agent works through `bench/arm_a.py`, every step lands in the shared ledger, the chain verifies and `bench/report.py` scores it.

**This is not an experiment.** The runner is a stub that returns fixed scores (`stub_runner.py`). It tests the pipeline, not a science question.

- **Run:** `A-demo-5`, 2026-10-04, Omnigent 0.16.0, Claude Code via subscription (`claude-sdk` harness), code at `9e52fce` on `main`.
- **Outcome:** `completed` in 35 s, not timed out. 9 events: hypothesis, then for each of 2 runs a committed prediction before `RUN_STARTED`, then the answer.
- **Checks:** `python -m cli.verify` → `chain OK, 9 events`. `bench/report.py` → `completed: True, attempts: 2, valid_experiments: 2, prereg_violations: 0`.
- **Screen recording:** shared separately (too large for the repo).

## Files

| Path | What it is |
|---|---|
| `spec.json`, `stub_runner.py` | Inputs used for the run |
| `A-demo-5/prompt.md` | The filled baseline prompt the agent received |
| `A-demo-5/omni_agent/config.yaml` | The Omnigent agent config the launcher wrote |
| `A-demo-5/launcher.json` | The `omni run` command, exit code and outcome |
| `A-demo-5/events.jsonl` | Ledger export (hash chained; the `.db` is left out per `AGENTS.md`) |
| `A-demo-5/agent_stdout.log`, `final_report.md`, `answer.json` | The agent's output, report and submitted answer |
| `A-demo-5/manifest.json`, `run_records.jsonl`, `decisions.jsonl` | Episode manifest, raw runner results, recorded decisions |

## Reproduce

Setup once per machine: see "Running with Omnigent (setup notes)" in `bench/README.md` (`omni setup` with Subscription as the default; no custom `ANTHROPIC_BASE_URL` in `~/.claude/settings.json`). Then, from the repo root, in an environment with `requirements.txt` installed:

```bash
mkdir -p /tmp/armA && cp results/omnigent-demo/stub_runner.py results/omnigent-demo/spec.json /tmp/armA/
PYTHONPATH=/tmp/armA python bench/launch_arm_a.py --spec /tmp/armA/spec.json --seed 1 --episode /tmp/armA/ep --run-id A-demo
python -m cli.verify A-demo --db /tmp/armA/ep/ledger.db
python -c "import sys; sys.path.insert(0,'bench'); import report; print(report.episode_metrics('/tmp/armA/ep', None))"
```

Use a new `--episode` folder and `--run-id` for each run; the launcher refuses to reuse one.
