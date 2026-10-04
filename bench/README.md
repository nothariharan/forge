# Benchmark

No benchmark results are present yet.

- **Protocol:** [`PROTOCOL.md`](PROTOCOL.md) defines the arms, metrics with denominators, budget, seeds, analysis, failure handling and artifact layout. It is a draft until the science contract is locked.
- **Report:** `python3 bench/report.py results/bench/<bench_id>` computes every metric from the episode artifacts and writes `metrics.json` per episode plus `report.md` / `report.json`. Uses the standard library only.
- **Oracle:** `python3 bench/oracle.py <spec.json> --out results/bench/<bench_id>` runs every candidate on every seed (resumable) and writes `oracle.json`, the ground truth for correctness scoring.
- **Baseline (arm A):** [`baseline_prompt.md`](baseline_prompt.md) is the prompt template (reviewed by Hari; stays a draft until the science question is locked). `bench/arm_a.py` gives the baseline agent commands to record hypotheses and predictions, run experiments through the same runner as FORGE, log decisions and submit its answer. Events go through the shared ledger (`core/ledger.py`) and are exported to `events.jsonl` in the episode folder.
- **Launcher (arm A):** `python3 bench/launch_arm_a.py --spec <spec.json> --seed <n> --episode results/bench/<bench_id>/A/seed-<n> [--dry-run]` fills the prompt (refuses any missing placeholder), starts the episode with the budget enforced by `arm_a.py`, writes a one-agent Omnigent config, runs it headless (`omni run <agent_dir> --no-session -p <prompt>`, stdin closed; run `omni setup` once first) with a hard timeout at the wall-clock budget, and closes episodes that end without an answer as `budget_exhausted` or `aborted`.
- **Arm B (FORGE) launcher:** `python3 bench/launch_arm_b.py --spec <spec.json> --seed <n> --episode results/bench/<bench_id>/B/seed-<n>` runs FORGE headless on the same task, with the same timeout and close logic as arm A, and exports its ledger run for scoring.
- **Full benchmark:** `python3 bench/run_bench.py --spec <spec.json> --bench-id <id> --seeds 1 2 3 4 5 --oracle-spec <oracle_spec.json>` runs both arms over all seeds in alternating order, builds the oracle and writes the report. It is resumable and has a `--dry-run` mode.
- **Lite benchmark (TESS, seeds 1–3):** `python3 bench/run_lite_seed.py --seed <n>` runs arm A and arm B for one seed into `results/bench-lite/seed-<n>/` with `command.json` and `summary.json`; it refuses an unpinned snapshot or an existing seed folder. `python3 bench/aggregate_lite.py` combines the seeds with the fixed claim wording and labels. See `PROTOCOL_TESS.md` section 12.
- **Colab:** [`colab_lite.ipynb`](colab_lite.ipynb) runs the pre-lock (open internet for the NASA archive) and one seed in Google Colab: clone with a `GH_TOKEN` Colab secret, `omni setup` in the Colab terminal, run, push the results branch.
- **Citations:** `python3 tools/citation_check.py <refs.json | report.md> -o citations.json` (needs `requests` and internet access).
- **Tests:** `python3 -m pytest -q tests/`

## Running with Omnigent (setup notes)

Verified end to end by Ish on 2026-10-04: a stub episode completed in 32 s with a hypothesis, 2 preregistered runs and an answer. It produced 9 events, the chain verified, and `report.py` counted 2 valid experiments and 0 preregistration violations.

- Run `omni setup` once and set **Subscription** as the default credential.
- A custom `ANTHROPIC_BASE_URL` in `~/.claude/settings.json` overrides Omnigent's credential. Remove it, or the agent can fail to authenticate.
- When the agent dies (for example with an auth error), `omni` can still exit 0. The launcher then records the episode as `aborted`, with the reason and the end of the agent's output in `launcher.json` (`failure_reason`) and in the `RUN_COMPLETED` summary.
- The agent's report belongs in `$FORGE_EPISODE_DIR/final_report.md`. A report written to the repo root is moved into the episode, so episodes don't overwrite each other.

## Planned arms
- A: single-agent baseline.
- B: FORGE multi-agent harness under the same task and documented budget.

## Reporting
Every number is computed from raw artifacts under `results/bench/`. Report denominators and uncertainty. Do not infer discovery quality from throughput alone.
