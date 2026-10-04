# Benchmark protocol: single agent vs FORGE

**Status:** draft v0.1, not locked. Fields marked **TBD (science)** depend on the science contract (`docs/coordination/SCIENCE_CONTRACT.md`) and are filled in once Hari locks the question. The protocol is committed and frozen **before** any comparative run; later changes get a dated entry in the change log at the bottom.

**Challenge target:** Track 03 “Agentic Scientific Discovery” (`docs/references/reference-02.pdf`). The benchmark contributes to the 20% discovery acceleration/learning and 15% rigor criteria. It must name a real bottleneck, define a defensible denominator, compare against a baseline, report actual improvement and cost, and connect results to a next experiment. The 10× target is a moonshot, not a required or assumed result. The science candidate and protocol fields below remain unapproved until Hari and Akshat lock them together.

**Owner:** Akshat (`work/benchmark`). **Depends on:** science contract (Hari), event schema (Ish), Omnigent runner (Saksham).

## 1. Claim under test

> On the locked research question, under a matched budget, the FORGE multi-agent harness (arm B) produces a better and/or faster research loop than a single plain agent (arm A).

We report whatever we observe, including B being slower or worse. No 10x claim. The headline number is the observed ratio with its uncertainty, its baseline, its sample size, and its cost.

## 2. Arms

| Arm | What it is | What it gets |
|---|---|---|
| **A: baseline** | One Claude Code agent, one session, plain prompt (`bench/baseline_prompt.md`): the question, the allowed tools, the budget, and the required output format. It acts through `bench/arm_a.py`. No planner, no referee, no consensus, no policy gates beyond the shared sandbox limits. | Same model, tools, data, budget and seed list as B. |
| **B: FORGE** | Full harness through Omnigent: Librarian, Hypothesizer, Referee, Planner, Experimenter, Analyst, Safety, with policies P1 to P6. | Same as A. |
| C1 to C3 (optional ablations) | B minus Referee; B with a random-order Planner; B with a single Analyst (no consensus). | Run only if time allows after A and B are complete. |

**Matched across arms** (recorded per episode in `manifest.json`):

- Model ID and version for every agent call (same model family in both arms, judge excepted).
- Tool set: the same experiment runner (`tools/openml_run.py`), the same literature tools, the same sandbox limits.
- Task, dataset version, split protocol and metric: **TBD (science)**.
- Budget: the same wall-clock cap, token/USD cap and maximum experiment count (section 5).
- Seed list (section 6).

Unavoidable differences, for example B's extra coordination tokens, are **counted against B's budget**, not exempted.

## 3. Unit of replication

An **episode** is one arm run from the question to a final report, under one seed. Each episode yields one row of metrics. Arms are compared on paired episodes (same seed, A vs B).

## 4. Metrics

Every metric states its numerator and denominator. "Timed window" means from the `RUN_CREATED` event to the `RUN_COMPLETED` event (or the budget cutoff), excluding setup, installs and dataset downloads that happen before the window opens.

### Definitions used below

- **Valid experiment:** a run that (a) had a prediction and falsifier committed *before* it started (a `PREDICTION_COMMITTED` event precedes its `RUN_STARTED`), (b) exited successfully, and (c) produced the locked metric on the locked split. Anything else counts as an *invalid attempt* and is still reported.
- **Hypothesis tested:** a distinct hypothesis ID with at least one valid experiment.
- **Reference:** any DOI, arXiv ID, OpenAlex ID or URL cited as support in the episode's evidence or final report.

### Primary metric (exactly one, locked before runs)

**TBD (science), pick one with Hari.** Candidates, in order of preference:

1. **Decision correctness:** does the episode's final recommended answer match the oracle answer (section 7)? Binary per episode; reported as k/N per arm.
2. **Experiments to reach the top candidate:** the number of valid experiments until the episode first selects a candidate within the practical threshold of the oracle best (section 7). Censored at the budget cap; censored episodes are reported as such, never dropped.

### Secondary metrics

| ID | Metric | Numerator | Denominator |
|---|---|---|---|
| S1 | Valid experiments per hour | valid experiments | timed wall-clock hours |
| S2 | Hypotheses tested per hour | hypotheses tested | timed wall-clock hours |
| S3 | Unresolvable reference rate | references that fail to resolve (DOI/arXiv/OpenAlex lookup) | all references cited |
| S4 | Unsupported quote rate | resolvable references whose quoted span is not found in the source | resolvable references that come with a quote span |
| S5 | KNOWN rate | proposed hypotheses that the common novelty check (section 8) labels KNOWN | proposed hypotheses |
| S6 | Invalid attempt rate | invalid attempts | all experiment attempts |
| S7 | Preregistration violations | runs started without a committed prediction and falsifier | all experiment attempts |
| S8 | Result-driven replans | results followed by a recorded change of next decision (`REPLAN`) | valid experiments |
| S9 | Cost | input/output tokens, USD, compute seconds, timed wall time | per episode, and per valid experiment |
| S10 | Human time | seconds a human spent on approvals or interventions | per episode |

S3 and S4 are deliberately separate: an ID that resolves can still fail to support the claim it is cited for.

### Speedup multiplier (what goes on the slide)

- **Throughput multiplier** = median over seeds of S1(B) / S1(A).
- **Time-to-answer multiplier** = timed wall time for A to reach the top candidate / the same for B, on episodes where both arms reach it. Episodes where an arm never reaches it are reported separately.

Both multipliers are reported with a CI (section 9), next to the quality metric. Throughput alone is never presented as discovery quality.

## 5. Budget (identical for both arms)

| Item | Value |
|---|---|
| Wall-clock cap per episode | **TBD (science)**; proposal: 30 min |
| Token / USD cap per episode | **TBD**; proposal: equal USD cap, all agents' calls summed |
| Max experiment attempts per episode | **TBD (science)** |
| Compute limits per experiment | Same sandbox time/memory caps as the Experimenter (policy P5) |
| Human approval wait | Recorded separately. Metrics are reported both including and excluding it. |

The budget cutoff ends the episode; whatever the arm has produced at that point is its final answer. If no answer exists, the episode is scored as "no answer".

## 6. Seeds and run order

- **Seeds:** `1, 2, 3, 4, 5` (N=5 per arm). Minimum acceptable N=3; with fewer, results are labeled **preliminary**.
- The seed fixes the dataset split, the model training RNG and any sampled choices inside our tools. **LLM sampling is not seed-controllable**: we record the model, temperature and request IDs, and treat the remaining nondeterminism as part of the variance we measure.
- **Run order:** interleave arms (A1, B1, A2, B2, ...) in the same time window, so API latency and load drift affect both arms equally.

## 7. Oracle / ground truth

Correctness is scored against a **deterministic oracle**, never LLM self-grading.

- The oracle is an exhaustive (or large fixed) sweep of the candidate space on the locked task and seeds, run once by the benchmark harness outside both arms.
- It defines the oracle-best candidate and the set of candidates within the practical threshold.
- **TBD (science):** candidate space, practical threshold, metric direction.
- Tool: `python3 bench/oracle.py <spec.json> --out results/bench/<bench_id>`. Every (candidate, seed) result is appended to `sweep_runs.jsonl`, including failures. A candidate with any failed seed is listed but cannot be the best. The top set is the complete candidates whose mean is within the practical threshold of the best mean.

If the question has no sweepable candidate space, the primary metric falls back to a pre-specified rubric scored **blind to arm** by a human, with the rubric committed here before runs.

## 8. Citation and novelty checks (common to both arms)

- `tools/citation_check.py` runs on every episode's references after the episode ends, with the same code for both arms. It reports, per reference: resolved yes/no, the resolver used, and quote span found yes/no/not given.
- The novelty check runs the same queries and sources for both arms, with search scope and date recorded. Its labels are search results, not proof of novelty.
- Any manual review is done on outputs with the arm label removed.

## 9. Analysis

- Per arm, per metric: all per-seed values, plus the mean and median.
- **Paired comparison:** per-seed difference (B - A) and ratio (B / A). The 95% CI comes from a paired bootstrap over seeds (10,000 resamples). With N=3 to 5 these intervals are wide, and we say so.
- **Rates (S3 to S7):** pooled counts per arm with Wilson 95% intervals, plus the per-episode values.
- **Binary primary (decision correctness):** k/N per arm with exact (Clopper-Pearson) intervals. No significance claim at N=5.
- One primary metric, so no multiple-comparison correction on it. Secondary metrics are descriptive.
- Ablations (C1 to C3) are compared with B in the same way.

## 10. Failures and exclusions

- **Keep everything.** Crashed, timed-out and no-answer episodes stay in the denominator.
- The only allowed re-run: an infrastructure failure *before the first agent action* (for example a container that never started). Every re-run is logged with the reason in the bench manifest.
- No dropping, editing or cherry-picking episodes after seeing their results.

## 11. Artifacts per episode

Stored under `results/bench/<bench_id>/<arm>/seed-<n>/`:

| File | Contents |
|---|---|
| `manifest.json` | bench ID, arm, seed, git commit, model IDs, tool versions, dataset/task ID and version, budget, start/end timestamps, re-run reason if any |
| `events.jsonl` | Ledger events (`schemas/event.schema.json`). Arm A is wrapped in a thin logger that emits the same event types it can produce. |
| `run_records.jsonl` | One record per experiment attempt, valid or not |
| `final_report.md` | The arm's final answer and cited evidence, as produced |
| `usage.json` | Token, USD and compute totals per agent |
| `citations.json` | Output of `tools/citation_check.py` |
| `metrics.json` | Metrics computed by `bench/report.py` from the files above |

`bench/report.py` computes every reported number from these files only. No hand-entered numbers.

## 12. Threats to validity (to be repeated in the README)

- Small N: 3 to 5 episodes per arm give wide intervals.
- One task and one domain: the result may not transfer.
- The baseline prompt matters: a weak baseline prompt inflates the gap. The arm A prompt is committed in `bench/` before runs and reviewed by someone outside the benchmark lane.
- LLM nondeterminism and API drift between runs.
- The novelty check covers only the searched sources and dates.
- The oracle sweep defines "correct" only within the chosen candidate space.

## 13. Open questions for Hari (science)

1. Can the provisional astronomy direction be expressed with an observed outcome, object-disjoint held-out cohort, and a defensible prior-art gap? See `docs/coordination/SCIENCE_DECISION_PACKET.md`; its old precision-transfer numbers are withdrawn.
2. Once Hari locks a valid question: task/dataset version, split protocol, primary metric/direction/threshold, candidate space and oracle affordability.
3. Primary benchmark outcome: decision correctness or experiments/time to reach the oracle top set; define the bottleneck and denominator explicitly.
4. Matched wall-clock/token/USD/compute budgets and maximum attempts.
5. Repetitions, paired seeds, uncertainty method, and whether `tools/openml_run.py` implements them as specified.
6. Review `bench/baseline_prompt.md` independently of the benchmark lane before protocol freeze.
7. Migrate `bench/arm_a.py` to `Ledger.append` while preserving payload schemas and verify/import behavior.

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-04 | Draft v0.1 | Akshat |
