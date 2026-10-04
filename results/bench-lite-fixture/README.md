# Lite benchmark protocol: smoke-scale run on a synthetic fixture

**What this is:** one run of the lite benchmark protocol (`bench/PROTOCOL_TESS.md` section 12), FORGE (arm B) vs a single-agent baseline (arm A), on the **synthetic TESS-like fixture** from `tests/tess_fixture.py`. **It is not the TESS task and not a benchmark result.** The NASA archive was unreachable from the run environment, so the real TOI snapshot was never fetched or pinned. Preliminary, n=3 seeds.

Run by Akshat on 2026-10-04, 11:00–11:22 UTC.

## Setup (identical for every episode)

| Item | Value |
|---|---|
| Data | `data/toi_fixture.csv`: `make_fixture(n_hosts=2600, seed=7)`, sha256 `bd9aba94f7ad727a3106317e12def93b2b51854ce47f23feeffc23572bfc0390` |
| Ground truth | `prelock/`: `tools/tess_prelock.py --no-fetch` on the fixture. Gap −0.0002, 95% CI [−0.006, 0.005]; γ=0 control −0.0025; all lock checks pass. Correct answers: `no_correction`, `lr_naive`, `hgb_naive` |
| Agents | omni 0.16.0, `claude-sonnet-5-5` for every agent in both arms (arm B runs a copy of `omnigent/forge` with every harness set to `claude-sdk`) |
| Code | commit `1cde3962a059dab4463aa6ca1b8f4a04a12fd53c` on `bench/arm-b-runnable`, clean tree; Python `.venv` from `requirements.txt` + `requirements-science.txt` for both arms |
| Budget | 10 min wall clock and 10 experiments per episode, both arms; arm B's P6 gate auto-approved as `harness` (no human in either arm) |
| Lock / spec | `lite_lock.json`, `spec_fixture.json` (the commands below read them from a scratch folder; these are byte-for-byte copies) |
| Leak control | the ground truth lived outside the repository during the episodes; agent output was scanned for oracle mentions (none found) |

Exact command per seed: `seed-N/command.json` (`report.md` lists them too). Seeds 1–3 ran **at the same time on one machine**.

## Results (`report.md`, `report.json`)

| | Arm A (single agent) | Arm B (FORGE) |
|---|---|---|
| Correct answer | 3/3 | 1/3 |
| Episodes finished with an answer | 3/3 | 1/3 (2 budget_exhausted) |
| Valid experiments per seed | 2, 3, 2 | 1, 0, 0 |
| Valid experiments / hour (median) | 24.4 | 0 |
| Preregistration violations | 0 | 0 |
| Wall time per episode (s) | 347, 293, 295 | 387, 630, 630 |
| Cost | n/a (usage not captured) | n/a |

On this fixture and with these settings, **the baseline did better than FORGE.** No speedup or correctness claim for FORGE follows from this run.

## Why arm B fell short (from the event timelines)

- Every gradient-boosting (`hgb`) experiment, in both arms, failed to finish within the budget. The three seeds ran in parallel on one machine, and `hgb` is the slow model.
- Arm A abandoned its stalled `hgb` runs (these are its "invalid attempts") and switched to logistic regression runs, which returned in about 30–90 s. It answered correctly in about 5 minutes every time.
- In seeds 2 and 3, FORGE's planner chose an `hgb` experiment first, and the experimenter waited on that one run until the budget ran out. FORGE spends about 2 minutes on hypothesis, prediction, selection and gate before its first experiment starts, and it has no way to abandon a slow run.

## Limitations

- Synthetic fixture, not TESS data. On this fixture, "no correction" is correct, which favours an agent that stops early.
- Running the seeds in parallel slowed every experiment and hurt arm B more. A sequential run, or a per-experiment time limit, would be a fairer test of the protocol.
- n=3 seeds: wide intervals (for example, correctness B 1/3 with CI [0.008, 0.906]).
- Before this run, three short smoke episodes (not counted, not kept) found and fixed arm B wiring problems on `bench/arm-b-runnable`: the gate refused the runner, the evidence step blocked without a literature tool, and three agents were on an uninstalled `codex` harness. A label-scoring bug was also fixed. No counted episode was re-run.
