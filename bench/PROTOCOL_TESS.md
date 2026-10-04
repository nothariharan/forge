# Protocol: TESS resolution-bias audit (proposed, v0.2)

- **Status:** **PROPOSED v0.3.1 for joint review. Not locked.** Runner built and validated on synthetic fixtures only (section 11). Nothing here is run as benchmark evidence until Hari and Akshat mark it locked in the change log.
- **Owner:** Akshat (benchmark + rigor), science review: Hari.
- **Date:** 2026-10-04.
- **Instantiates:** `bench/PROTOCOL.md` (arms, metrics, analysis, failure rules, artifacts apply unchanged unless stated here).
- **Built on:** `docs/coordination/SCIENCE_DECISION_PACKET.md` (gate update), `TESS_RESOLUTION_SHIFT_PREREGISTRATION.md` (T1), `schemas/examples/tess-reference-standard.json`, `schemas/examples/tess-resolution-shift.json`, `BENCHMARK_TESS_GATE_REVIEW.md`.

## 1. Question

> On the NASA Exoplanet Archive TESS TOI table, does evaluating a vetting classifier only on resolved TOIs overstate its accuracy on candidates that look like the unresolved pool, and which accuracy estimator corrects for it?

**Bottleneck this addresses:** follow-up time is allocated with vetting scores whose accuracy is measured on resolved objects. If that accuracy is overstated for the unresolved candidates the scores are actually used on, follow-up is mis-prioritized. The decision this informs: whether resolved-set accuracy can be quoted as triage accuracy, and if not, which correction to report instead.

## 2. Data

| Item | Value |
|---|---|
| Source | NASA Exoplanet Archive TAP, table `toi` |
| Snapshot | **Changed in v0.3.** T1's raw CSV (sha256 `485a05d6…`) was not saved, and the live archive keeps changing, so that hash cannot be reproduced. The snapshot is pinned when the cache is first created (`python tools/tess_bias_run.py --fetch` saves the raw bytes to `results/cache/toi.csv` and prints their sha256). That hash is recorded in the change log and set as `FORGE_TESS_SHA256`. The runner refuses any other file. T1 should be re-run on the same pinned file, so the shift result and T2 share one snapshot. |
| Rows | 8,148 TOIs; dispositions `CP` 813, `FP` 1,314, `FA` 100, `KP` 607, `PC` 4,813, `APC` 487, blank 14 |
| Features | The 39 numeric `pl_*` / `st_*` columns of the T1 primary arm. Excluded, as in T1: label, identifiers (`toi`, `tid`, `toipfx`), timestamps (`toi_created`, `rowupdate`, `release_date`), `*lim*` / `*symerr*` derivations, all-missing columns. |
| Grouping key | `tid` (TIC ID). Every split in this protocol is at host level. |

## 3. Labels (from the gate measurements)

| Set | States | Count | Basis |
|---|---|---:|---|
| Positive | `CP` | 813 | 88.7% host match in `pscomppars` vs 0.23% for `FP` |
| Negative | `FP`, `FA` | 1,414 | `FA` host-match rate (3.0%) behaves like `FP`, so it is a resolved non-planet |
| Excluded | `KP`, blank | 621 | `KP` label is a prior-survey catalog lookup, not TESS-side adjudication |
| Unresolved (no label) | `PC`, `APC` | 5,300 | Used only to fit the resolution model in section 4, never scored |

**Labeled cohort L** = 2,227 TOIs (CP vs FP+FA), 36.5% positive.

## 4. Split: semi-synthetic resolution split (replaces the temporal split)

A prospective temporal split is impossible: the table has no disposition date. The real unresolved pool has no truth labels. So the split recreates resolution bias **inside L, where truth is known**:

1. **Resolution model.** Fit the T1 model (logistic regression, median imputation, standardization) for resolved (`CP`, `FP`, `FA`) vs unresolved (`PC`, `APC`) on all labeled-or-unresolved rows. Take each L row's out-of-fold score `e(x)` from `tid`-grouped 5-fold CV, so no row is scored by a model that saw it.
2. **Host-level selection.** For replicate `r`, give each host in L a selection probability proportional to `mean(e)^γ` over its TOIs. Scale it so a fraction ρ = 0.30 of L's TOIs land in the pseudo-resolved set **R\***, matching the observed resolved share of non-`KP` TOIs. The rest are the pseudo-unresolved set **U\***. Hosts never straddle R\* and U\*.
3. **Mechanism strength γ.**
   - γ = 1 is primary: the selection fitted to the catalog.
   - γ = 0 is the **negative control**: random selection, so there should be no gap.
   - γ = 2 is a stress test.
4. **Replicates:** R = 20 per condition per seed, seeded `1000·seed + r`. See section 4.1 for how replicates and benchmark seeds fit together.

**What is measured, per replicate:**
- **True deployment AUC (changed in v0.3):** the mean, over the 5 grouped CV folds inside R\*, of each fold model's AUC on U\*. The naive estimate and the truth then come from the same fold models, trained on the same amount of data. Fitting the "true" model on all of R\* would make naive CV look pessimistic purely because of training size (a learning-curve bias), which is not resolution bias.
- **Naive estimate:** `tid`-grouped 5-fold CV AUC within R\* only. This is what a team would report today.
- **Gap Δ:** naive minus true. Positive means resolved-set evaluation overstates accuracy.

### 4.1 Replicates, seeds and uncertainty (added in v0.3)

There are two separate sources of uncertainty, and they are reported separately:

| Level | What varies | Count | Interval reported |
|---|---|---|---|
| **Simulation** (science result) | which hosts land in R\* vs U\*, and the CV folds | 20 replicates × 5 seeds = **100 simulated splits**, pooled | mean Δ ± 1.96 SE over the 100 replicate gaps (precision of the simulated mean), plus the 2.5–97.5 percentile of single replicates (how much one split can vary) |
| **Benchmark** (agent comparison) | the agents' behavior: which experiments they run and what they conclude | **5 paired episodes per arm** | `PROTOCOL.md` section 9: paired bootstrap over the 5 seeds, Clopper-Pearson for correctness k/5 |

- Episode seed *s* gives that episode's runner calls the replicate set `1000·s + 0…19`. Arm A and arm B share the seed, so they see identical simulated splits (paired).
- The oracle pools all 5 seeds' replicates (100) into one ground truth, and every episode is scored against it. An episode sees 20 of those 100 replicates, so its own numbers are noisier than the pooled truth. That is realistic, and both arms face it equally.
- The science result is computed once from the same 100 pooled replicates. It does not depend on what any agent did.
- The simulation interval is conditional on the snapshot and the mechanism. It says nothing about uncertainty from the covariate-shift assumption, which is a limitation, not a number.

### Limitations of this split (must travel with every result)

- **Selection on observables only.** It assumes resolution depends on the catalog features (covariate shift, with P(planet | features) the same in both sets). Selection on things outside the table, such as host brightness for ground follow-up or team priorities, is not captured, and that assumption cannot be tested with this data.
- **Current-snapshot features.** Feature values may have been refined after disposition, more so for confirmed planets. Absolute AUCs may be optimistic. Δ is computed within the same snapshot, but this caveat still applies to its size.
- **It recreates a second round of selection inside an already-selected cohort.** L is itself the resolved part of the catalog. The simulation shows how much bias this *kind* of selection produces, not the bias of the real resolved/unresolved boundary.
- **Asymmetric labels.** `FP` remains a TFOPWG committee judgment with no independent source. Positives have a host-level check only.
- **Scale.** L is 2,227 TOIs, so U\* carries about 1,560 per replicate. Replicate-to-replicate spread is part of the reported interval.
- **The simulation can only recreate selection the resolution model captures (added in v0.3).** The resolution model is linear (T1's). On a fixture where resolution strongly favored easy cases, a nonlinear pattern, the simulated gap was only 0.011 (section 11). A small simulated Δ is therefore not evidence that the real selection is harmless; it may be partly invisible to a linear model. A sensitivity arm with a nonlinear resolution model (e.g. gradient boosting) would probe this. It is **not** in the preregistered design; adding it is a decision for the lock review.

**Rejected alternative, kept as a sensitivity arm only:** a split on `toi_created` (train on TOIs created before the median date, test after) uses *current* labels. The later TOIs that are already resolved are the fastest-resolved ones, so this split measures resolution latency, not deployment conditions. It is reported, never used as the primary result.

## 5. Science estimand, prediction and stopping rule (T2)

- **Primary estimand:** mean Δ over the 20 replicates at γ = 1, for the logistic-regression vetting model, with the 2.5–97.5 percentile interval across replicates.
- **Practical threshold:** Δ ≥ 0.02 AUC counts as a meaningful overstatement.
- **Prediction (preregistered):** mean Δ ≥ 0.02 and the replicate interval excludes 0.
- **Falsifier:** mean Δ < 0.02, or the interval includes 0. That means no practically meaningful overstatement *under this mechanism*. It is reported as is, and does not establish that there is no real-world gap.
- **Validity check:** the γ = 0 control must give |mean Δ| < 0.01. Otherwise the pipeline is manufacturing a gap and the result is void.
- **Stopping rule:** run γ ∈ {0, 1, 2} × the two vetting models once, plus the `toi_created` sensitivity arm. Do not add models, features or tuning after seeing results.

## 6. Candidate space and oracle (for the benchmark)

The benchmark question both arms answer: **should resolved-set AUC be corrected before it is quoted as triage accuracy, and if so, with which estimator?** Its correct answer is computed exactly from the semi-synthetic truth (changed in v0.3, see below).

**Candidates** = `no_correction` + 2 vetting models × 3 estimators = **7**:

| Estimator | Estimate of deployment AUC |
|---|---|
| `naive` | grouped CV AUC within R\* |
| `iw` | grouped CV AUC within R\*, importance-weighted with w = p/(1−p), where p comes from a domain classifier trained to tell U\* features from R\* features (in reality: unresolved vs resolved features, which are observable), self-normalized. This is importance-weighted cross-validation (IWCV, Sugiyama, Krauledat & Müller 2007), an existing method |
| `iw_clip` | as `iw`, with weights clipped at their 95th percentile |

Vetting models: `lr` (logistic regression, as T1) and `hgb` (`HistGradientBoostingClassifier`, default settings, `random_state` = replicate seed).

**Oracle: a decision rule (changed in v0.3).** Built by `python tools/tess_bias_run.py --oracle results/bench/<id>/oracle.json` over the 100 pooled replicates (section 4.1):

1. Pool the gap Δ (`lr`, `naive`, γ = 1).
2. If mean Δ < 0.02, or its 95% interval includes 0: the correct recommendation is **report resolved-set AUC as is, with its interval**. The top set is {`no_correction`, `lr_naive`, `hgb_naive`}, which is one decision with three equivalent spellings.
3. Otherwise: the correct recommendation is a **correcting** estimator. The top set is every non-naive candidate within 0.005 of the lowest mean |estimate − true AUC|.

**Why the v0.2 oracle was replaced.** It was "lowest mean absolute error among 6 estimators, top set within 0.005". On the fixture it put **5 of 6** candidates in the top set, failing the pre-lock check. Each replicate's error (about 0.023) is almost all cross-validation noise on a few hundred objects. When there is no meaningful gap, there is nothing for a correction to fix, so "which estimator" has no real answer. The decision rule gives a single correct decision in both cases.

**Check before lock (revised):** on the pinned real snapshot, the oracle must return a single decision, and the γ = 0 control must stay within 0.01. If the gap lands within one standard error of 0.02, the decision is fragile; flag it before locking.

**Known weakness:** if the real-data answer is "no correction", an arm that always says "no correction" scores as correct without investigating. Decision correctness then separates the arms weakly. The secondary metrics carry the comparison: experiments and time to a preregistered, evidenced answer, preregistration violations, and result-driven replans. This must be stated next to any correctness result.

### Runner contract (science lane, `tools/tess_bias_run.py`)

```
run(task_id="tess-resolution-bias", params={"model": "lr"|"hgb", "estimator": "naive"|"iw"|"iw_clip", "gamma": 1}, seed)
  -> {"metrics": {"abs_error": float, "estimate": float, "true_auc": float, "naive_auc": float, "gap": float,
                  "gap_low": float, "gap_high": float, "abs_error_low": float, "abs_error_high": float, "share_r": float},
      "replicates": 20, "replicates_valid": int, "replicate_seeds": [...], "data_sha256": "...",
      "framing": "semi-synthetic simulation ...; not accuracy on real unresolved TOIs"}
```

Implemented in `tools/tess_bias_run.py` (v0.3). `_low` / `_high` are the 2.5–97.5 percentiles over that call's replicates. A replicate is invalid, and is reported as such, if either class has fewer than 10 TOIs in R\* or U\*.

The runner reads a cached copy of the snapshot (checked against the hash above), so episodes and the oracle never hit the network and always see the same data.

## 7. Two tests for the Planner, and why the first is chosen

| Test | What it runs | Cost | What changes next |
|---|---|---|---|
| **T2a: gap test** | `naive` estimator at γ = 1 and γ = 0, `lr` only | 2 runner calls | Gap below threshold → corrections are moot; report a null and stop. Gap present → run T2b. |
| **T2b: estimator comparison** | all estimators × both models at γ = 1 | 6 runner calls | Picks the estimator to recommend. |

T2a goes first: it is a third of the cost and decides whether T2b is worth running. That is the expected-learning-per-cost argument the brief asks for, and the ledger records the choice (`EXPERIMENT_SELECTED`). Both arms get the same runner and the same information. Neither is told which test to run first.

## 8. Benchmark parameters (fills `PROTOCOL.md` TBDs)

| Item | Value |
|---|---|
| Arms | A: single agent (`bench/launch_arm_a.py`), B: FORGE (`bench/launch_arm_b.py`), same model ID |
| Primary benchmark metric | **Decision correctness:** the final recommended candidate is in the oracle top set. k/N per arm, Clopper-Pearson interval. |
| Secondary | Experiments to reach the top candidate (censored at the cap); S1 valid experiments per hour; S3/S4 citation checks; S6/S7 invalid attempts and preregistration violations; S8 result-driven replans; S9 cost and wall time; S10 human time |
| Bottleneck / denominator | Time and experiments from the question to a correct, preregistered estimator recommendation. Denominators: timed wall-clock hours (RUN_CREATED → RUN_COMPLETED) and valid experiments |
| Headline multiplier | Time-to-correct-answer ratio A/B on episodes where both arms are correct, plus the S1 throughput ratio, each with a paired bootstrap CI. Reported next to correctness k/N and cost. |
| Seeds | 1, 2, 3, 4, 5. Minimum 3, otherwise labeled preliminary. Run order alternates (A1 B1, B2 A2, ...). |
| Budget per episode | 30 min wall clock, 10 experiment runs, the same USD cap for both arms (recorded; set when the model is fixed) |
| Stopping rule | An episode ends at the answer or the budget. The benchmark ends after 5 paired seeds. The only allowed re-run is an infrastructure failure before the first agent action. |
| Uncertainty | Benchmark: as `PROTOCOL.md` section 9, over the 5 paired seeds. Science: over 100 pooled replicates (section 4.1). |

## 9. The exact claims this can support

If the run goes as planned, these are the strongest statements allowed. Fill in the measured values and do not strengthen the wording:

1. **Science (simulation):** "On the TESS TOI snapshot of __ (sha256 __), under a semi-synthetic resolution mechanism fitted to current catalog fields, evaluating a vetting classifier only on resolved TOIs overstated its AUC on a deployment-like population by Δ = __ (95% interval over 100 simulated splits __–__). [If Δ ≥ 0.02:] An existing correction, importance-weighted cross-validation (Sugiyama et al. 2007), recovered that AUC within __ on average. [If Δ < 0.02:] Under this mechanism the overstatement was below the 0.02 practical threshold; because the resolution model is linear, this does not show that the real selection is harmless. This quantifies, in simulation, a selection effect that prior work describes qualitatively (`docs/coordination/REFEREE_RESOLUTION_BIAS.md`). It is not a measurement of accuracy on real unresolved candidates." Pick one bracketed branch to match the result.
2. **Benchmark:** "On this task, FORGE reached the oracle-correct recommendation in __/5 episodes vs __/5 for a single agent with the same model, tools and budget, taking __× the time (95% CI __–__) at __× the cost." If FORGE is slower or worse, that is the claim. If the correct answer is "no correction", also say that correctness alone separates the arms weakly (section 6).

**Not supported, whatever the numbers** (the Referee search found the method known and the phenomenon described qualitatively; only the quantification was not found, at listing level):
- that the correction method is new (IWCV is Sugiyama et al. 2007);
- "first" or "novel" wording about the bias itself;
- accuracy on real unresolved TOIs;
- triage-time (historical) shift;
- any planet discovery or validation;
- novelty of the resolution-bias question until the Referee search is done;
- any speedup outside this task.

## 10. Open items before lock

1. ~~**Hari:** review sections 4–7~~ done. γ 0/1/2, ρ = 0.30 and the 0.02 threshold stay provisional until lock.
2. ~~**Runner**~~ done: `tools/tess_bias_run.py`, validated on fixtures (section 11).
3. **Pre-lock oracle check on the real snapshot:** Hari runs `--fetch`, records the hash in the change log and in `bench/specs/tess_resolution_bias.json` (`data_ver`), re-runs T1 on that file, then runs `--oracle`. Lock only if it returns one decision and the γ = 0 control holds.
4. ~~**Referee search**~~ done: `docs/coordination/REFEREE_RESOLUTION_BIAS.md`. Verdict: partial overlap; claim wording in section 9 updated. A full-text / citation-chaining pass is optional.
5. ~~**Adapt the baseline prompt**~~ done (v0.2): no OpenML wording, `{ANSWER_OPTIONS}` = the oracle's 7 candidates. Task text is in `bench/specs/tess_resolution_bias.json`. The episode metric is `gap`, which every run reports. Freeze with this protocol.
6. **Provisional spec values to settle before lock:** the USD cap, and literature access. Both arms must get the same; the spec currently gives no literature tool, which only matches arm B if FORGE's Librarian is also offline for the benchmark.
7. **Arm B smoke run with real Omnigent (Ish + Saksham):** one FORGE episode on the fixture or the pinned snapshot via `bench/launch_arm_b.py`, checking it records the arm B contract items in `docs/coordination/BENCHMARK.md` (`candidate` in `RUN_COMPLETED`, `PREDICTION_COMMITTED` with `eid`, experiment cap).
8. **No speedup or comparison claim** until both arms have comparable real episodes under the locked protocol.

## 11. Runner validation on synthetic fixtures (v0.3)

`tools/tess_bias_run.py` implements the runner contract. It was validated on two **synthetic** TOI-shaped fixtures (`tests/tess_fixture.py`). These are not real TESS data, and no number below describes the real catalog. Raw output: `schemas/examples/tess-bias-fixture-validation.json`. Tests: `tests/test_tess_bias_run.py` (15 tests).

| Check (Hari's request) | Result on fixtures | Status |
|---|---|---|
| Host-level sampling well defined | R\* share = 0.30 ± one host's TOIs in every replicate; no host split across R\*/U\*; identical split for the same seed; separation increases with γ (tested for γ = 0, 1, 2) | **pass** |
| γ = 0 control within 0.01 | mean Δ −0.0025 (fixture 1) and +0.0018 (fixture 2), each over 100 pooled replicates, SE ≈ 0.003 | **pass** |
| 6-candidate oracle has a useful top set | v0.2 oracle: **5 of 6** candidates tied | **fail**, so the oracle was replaced by the decision rule (section 6) |
| Decision-rule oracle gives one decision | both fixtures: "no correction" (Δ = −0.0002 [−0.006, 0.005]; Δ = 0.0107 [0.005, 0.017]). The "correct with an estimator" branch is covered by unit tests | **pass** |

Other observations:
- **Single replicates are noisy:** per-replicate Δ spans about ±0.05. Pooling 100 replicates brings the SE to about 0.003, which is why the science result pools across seeds and a single episode's 20 replicates are treated as noisy evidence.
- **Weighting reduces bias but adds noise.** On fixture 2, `iw`/`iw_clip` cut the `lr` bias from 0.0107 to 0.0037 / 0.0029, but their mean absolute error is higher than naive's. That is why the oracle only prefers a correcting estimator when the gap is meaningful.
- **Runtime:** the full oracle (lr and hgb at γ = 1, lr at γ = 0, 5 seeds × 20 replicates) takes about 2 minutes per fixture on one CPU core. `hgb` dominates. Real L is about 1.8× the fixture's.

**Not validated:** anything on the real snapshot. Hari runs `--fetch`, pins the hash, then `--oracle`, before lock.

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-04 | v0.2 proposed: TESS resolution-bias instantiation | Akshat |
| 2026-10-04 | v0.3.1: Referee search done (partial overlap: IWCV method known, phenomenon described qualitatively, quantification not found); claim wording and the not-supported list updated; baseline prompt v0.2 and `bench/specs/tess_resolution_bias.json` added; open items refreshed | Akshat |
| 2026-10-04 | v0.3: snapshot pinned at first fetch (T1's raw CSV was not saved); true AUC from the same fold models as the naive estimate; section 4.1 on replicates vs seeds; oracle replaced by a decision rule after the fixture showed a 5-of-6 tie; linear-resolution-model limitation; fixture validation (section 11). γ 0/1/2, ρ = 0.30 and the 0.02 threshold stay provisional (Hari, review of sections 4–7) | Akshat |
