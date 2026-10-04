# Arm B smoke run (unofficial)

One FORGE (arm B) episode on the TESS task, run to check the full seven-agent loop before seed runs. **Not a benchmark result:** one seed, one experiment, and the TESS snapshot was fetched locally because the pin was not on `main` yet.

- **Run:** `B-smoke-5`, 2026-10-04, `python bench/launch_arm_b.py --spec <spec pinned to the snapshot below> --seed 1 --episode /tmp/armB/seed-1 --run-id B-smoke-5`
- **Omnigent:** 0.16.0, all seven agents on `claude-sdk` (Claude subscription), `FORGE_GATE_MODE=auto`
- **Code:** branch `orch/all-claude-agents` (PR #24) with its fixes applied
- **Snapshot:** `nasa-toi@485a05d6f94cf3399523df75e314c533e2d8ffad05e217a2e59517580a90f609`, fetched with `tools/tess_bias_run.py --fetch`. Replace with the official pin when it lands.
- **Outcome:** `completed` in 4 min 48 s, not timed out. 13 events.

## Hari's checks

| Check | Result |
|---|---|
| `RUN_COMPLETED` includes a candidate | Pass (`lr_iw_clip`) |
| Every experiment has `PREDICTION_COMMITTED` with its `eid` first | Pass (E1 committed at seq 5, started at seq 8) |
| 10-experiment cap enforced | Pass (1 experiment) |
| Ledger chain verifies | Pass |

## What the agents did

Librarian (no retrieval tool, so an honest empty evidence packet) → hypothesizer → referee (UNCERTAIN, no search possible) → planner (prediction gap 0.04 ± 0.03, then E1 = `lr`, `naive`, gamma 2) → safety gate (auto-approved, logged as `harness`) → experimenter (gap 0.039, 95% range 0.016 to 0.061) → analyst (FINDING: SUPPORTS; REPLAN) → director (RUN_COMPLETED).

Observations for the protocol:
- Arm B used 1 of 10 experiments and stopped at about 5 minutes of a 10-minute budget, reporting the clock as exhausted. Each experiment cycle through seven agents takes about 3 to 4 minutes.
- The answer `lr_iw_clip` is not backed by a measurement; the agent says so in its summary.

## Files

`launcher.json` (command, exit code, outcome), `events.jsonl` (ledger export; the `.db` is left out per `AGENTS.md`), `prompt.md` (task message), `manifest.json`, `agent_stdout.log` (director's final report), `answer.json` (scored answer).
