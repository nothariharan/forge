# Lite benchmark: smoke-scale run (n=3 seeds) of the lite benchmark protocol on a synthetic TESS-like fixture, FORGE vs a single-agent baseline; not the TESS task and not a benchmark result

**Labels: synthetic fixture, not TESS data, preliminary.** Results are on a synthetic TESS-like fixture (tests/tess_fixture.py), not the TESS snapshot; they show how the two arms run the protocol, not anything about TESS. No claim beyond this task and these seeds.

- Budget per episode, same for both arms: see command.json and summary.json in each seed folder.
- Cost: n/a (usage is not captured).
- Not lockable or preliminary means no correctness or speedup claim is made from these numbers.
- Failed, timed-out and budget_exhausted episodes are included; nothing was re-run.
- Literature tooling was not provided to either arm; this compares the protocol (committed predictions, budget, ledger, approval gate), not citation quality.

- Arm B's P6 gate is auto-approved by the harness (no human in either arm).
- Ground truth during the episodes: not hidden; it was kept outside the repository, but agents ran without a sandbox and could in principle have read it. Agent logs, events and arm B handoff files are scanned for oracle mentions.

## Episodes

| Seed | A outcome | B outcome | Oracle mentions in agent output | Command |
|---|---|---|---|---|
| 1 | completed | completed | none | `/home/user/forge/.venv/bin/python bench/run_lite_seed.py --seed 1 --spec /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/spec_fixture.json --out results/bench-lite-fixture --oracle /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/prelock/oracle.json --lock /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/lite_lock.json --model claude-sonnet-5-5 --arm-a-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}' --arm-b-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}'` |
| 2 | completed | budget_exhausted | none | `/home/user/forge/.venv/bin/python bench/run_lite_seed.py --seed 2 --spec /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/spec_fixture.json --out results/bench-lite-fixture --oracle /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/prelock/oracle.json --lock /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/lite_lock.json --model claude-sonnet-5-5 --arm-a-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}' --arm-b-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}'` |
| 3 | completed | budget_exhausted | none | `/home/user/forge/.venv/bin/python bench/run_lite_seed.py --seed 3 --spec /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/spec_fixture.json --out results/bench-lite-fixture --oracle /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/prelock/oracle.json --lock /tmp/claude-0/-home-user-forge/d6aac372-7b2b-59ae-9a71-bff81d41d68d/scratchpad/fixrun/lite_lock.json --model claude-sonnet-5-5 --arm-a-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}' --arm-b-cmd 'omni run {agent_dir} --no-session --model claude-sonnet-5-5 -p {prompt}'` |

## Setup (from each seed's command.json)

| Seed | omni | model | code commit | snapshot |
|---|---|---|---|---|
| 1 | 0.16.0 | claude-sonnet-5-5 | 1cde3962a059 | bd9aba94f7ad |
| 2 | 0.16.0 | claude-sonnet-5-5 | 1cde3962a059 | bd9aba94f7ad |
| 3 | 0.16.0 | claude-sonnet-5-5 | 1cde3962a059 | bd9aba94f7ad |

Paired seeds: [1, 2, 3] (N=3). Intervals are 95%. Paired bootstrap over seeds (10,000 resamples) for per-seed metrics; Wilson for pooled rates; Clopper-Pearson for correctness.

**Throughput multiplier (median S1 B/A): 0x, CI [0, 0.449], from 3 paired seeds.**

## Per-seed metrics

| Metric | A per seed | B per seed | median diff (B-A) [CI] | median ratio (B/A) [CI] |
|---|---|---|---|---|
| S1 valid experiments / hour | 20.7, 36.9, 24.4 | 9.31, 0, 0 | -24.4 [-36.9, -11.4] | 0 [0, 0.449] |
| S2 hypotheses tested / hour | 10.4, 12.3, 12.2 | 9.31, 0, 0 | -12.2 [-12.3, -1.06] | 0 [0, 0.898] |
| S3 unresolvable reference rate | n/a, n/a, n/a | n/a, n/a, n/a | n/a | n/a |
| S4 unsupported quote rate | n/a, n/a, n/a | n/a, n/a, n/a | n/a | n/a |
| S6 invalid attempt rate | 0.5, 0.25, 0.5 | 0.5, 1, 1 | 0.5 [0, 0.75] | 2 [1, 4] |
| S7 preregistration violations | 0, 0, 0 | 0, 0, 0 | 0 [0, 0] | n/a |
| S8 result-driven replans / valid experiment | 0, 0, 0 | 1, n/a, n/a | 1 [1, 1] | n/a |
| S9 cost (USD) | n/a, n/a, n/a | n/a, n/a, n/a | n/a | n/a |
| S9 tokens | n/a, n/a, n/a | n/a, n/a, n/a | n/a | n/a |
| S9 timed wall time (s) | 347, 293, 295 | 387, 630, 630 | 335 [39.6, 337] | 2.13 [1.11, 2.15] |
| S9 USD / valid experiment | n/a, n/a, n/a | n/a, n/a, n/a | n/a | n/a |
| S10 human approval time (s) | 0, 0, 0 | 0, 0, 0 | 0 [0, 0] | n/a |
| Experiments to reach top candidate | 1, 1, 1 | 1, not reached, not reached | 0 [0, 0] | 1 [1, 1] |

## Pooled counts

| Arm | Episodes (completed) | Unresolvable refs | Unsupported quotes | Invalid attempts | Correct answers | Reached top candidate |
|---|---|---|---|---|---|---|
| A | 3 (3) | n/a | n/a | 5/12 [0.193, 0.68] | 3/3 [0.292, 1] | 3/3 [0.292, 1] |
| B | 3 (1) | n/a | n/a | 3/4 [0.301, 0.954] | 1/3 [0.0084, 0.906] | 1/3 [0.0084, 0.906] |

## Notes

- Crashed, timed-out and no-answer episodes are included in every denominator.
- S3/S4 come from tools/citation_check.py; network errors are excluded from the denominator and listed per episode.
- Quote checks cover the abstract or supplied full text only.
- Throughput is not discovery quality; read it alongside correctness and experiments to the top candidate.
