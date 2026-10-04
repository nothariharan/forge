# Protocol: TESS resolution-bias audit (proposed, v0.2)

- **Status:** **PROPOSED for joint review. Not locked.** Nothing here is run as benchmark evidence until Hari and Akshat mark it locked in the change log.
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
| Snapshot | The T1 retrieval: 2026-10-04T06:01:46Z, raw CSV sha256 `485a05d6f94cf3399523df75e314c533e2d8ffad05e217a2e59517580a90f609`. The runner refuses a different hash unless the protocol change log records a new snapshot. |
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
4. **Replicates:** R = 20 per condition, seeded `1000·episode_seed + r`.

**What is measured, per replicate:**
- **True deployment AUC:** fit the vetting model on all of R\*, score U\*, compute AUC against true labels.
- **Naive estimate:** `tid`-grouped 5-fold CV AUC within R\* only. This is what a team would report today.
- **Gap Δ:** naive minus true. Positive means resolved-set evaluation overstates accuracy.

### Limitations of this split (must travel with every result)

- **Selection on observables only.** It assumes resolution depends on the catalog features (covariate shift, with P(planet | features) the same in both sets). Selection on things outside the table, such as host brightness for ground follow-up or team priorities, is not captured, and that assumption cannot be tested with this data.
- **Current-snapshot features.** Feature values may have been refined after disposition, more so for confirmed planets. Absolute AUCs may be optimistic. Δ is computed within the same snapshot, but this caveat still applies to its size.
- **It recreates a second round of selection inside an already-selected cohort.** L is itself the resolved part of the catalog. The simulation shows how much bias this *kind* of selection produces, not the bias of the real resolved/unresolved boundary.
- **Asymmetric labels.** `FP` remains a TFOPWG committee judgment with no independent source. Positives have a host-level check only.
- **Scale.** L is 2,227 TOIs, so U\* carries about 1,560 per replicate. Replicate-to-replicate spread is part of the reported interval.

**Rejected alternative, kept as a sensitivity arm only:** a split on `toi_created` (train on TOIs created before the median date, test after) uses *current* labels. The later TOIs that are already resolved are the fastest-resolved ones, so this split measures resolution latency, not deployment conditions. It is reported, never used as the primary result.

## 5. Science estimand, prediction and stopping rule (T2)

- **Primary estimand:** mean Δ over the 20 replicates at γ = 1, for the logistic-regression vetting model, with the 2.5–97.5 percentile interval across replicates.
- **Practical threshold:** Δ ≥ 0.02 AUC counts as a meaningful overstatement.
- **Prediction (preregistered):** mean Δ ≥ 0.02 and the replicate interval excludes 0.
- **Falsifier:** mean Δ < 0.02, or the interval includes 0. That means no practically meaningful overstatement *under this mechanism*. It is reported as is, and does not establish that there is no real-world gap.
- **Validity check:** the γ = 0 control must give |mean Δ| < 0.01. Otherwise the pipeline is manufacturing a gap and the result is void.
- **Stopping rule:** run γ ∈ {0, 1, 2} × the two vetting models once, plus the `toi_created` sensitivity arm. Do not add models, features or tuning after seeing results.

## 6. Candidate space and oracle (for the benchmark)

The benchmark question both arms answer is **which accuracy estimator to use**. Its correct answer can be computed exactly from the semi-synthetic truth.

**Candidates** = 2 vetting models × 3 estimators = **6**:

| Estimator | Estimate of deployment AUC |
|---|---|
| `naive` | grouped CV AUC within R\* |
| `iw` | grouped CV AUC within R\*, importance-weighted with w = p/(1−p), where p comes from a domain classifier trained to tell U\* features from R\* features (in reality: unresolved vs resolved features, which are observable), self-normalized |
| `iw_clip` | as `iw`, with weights clipped at their 95th percentile |

Vetting models: `lr` (logistic regression, as T1) and `hgb` (`HistGradientBoostingClassifier`, default settings, `random_state` = replicate seed).

- **Oracle metric:** absolute error |estimate − true deployment AUC|, averaged over replicates at γ = 1. Lower is better.
- **Oracle:** `bench/oracle.py` with `direction: minimize`, `practical_threshold: 0.005`. The top set is every candidate within 0.005 of the best mean error.
- **Check before lock:** if the top set holds more than 2 of the 6 candidates, the estimators are not distinguishable at this scale and the question is too flat to separate the arms. Revise before locking.

### Runner contract (science lane, `tools/tess_bias_run.py`)

```
run(task_id="tess-resolution-bias", params={"model": "lr"|"hgb", "estimator": "naive"|"iw"|"iw_clip", "gamma": 1}, seed)
  -> {"metrics": {"abs_error": float, "estimate": float, "true_auc": float, "naive_auc": float, "gap": float},
      "replicates": 20, "data_sha256": "..."}
```

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
| Uncertainty | As `PROTOCOL.md` section 9 |

## 9. The exact claims this can support

If the run goes as planned, these are the strongest statements allowed. Fill in the measured values and do not strengthen the wording:

1. **Science (simulation):** "On the 2026-10-04 TESS TOI snapshot, under a semi-synthetic resolution mechanism fitted to current catalog fields, evaluating a vetting classifier only on resolved TOIs overstated its AUC on a deployment-like population by Δ = __ (95% replicate interval __–__). The `__` estimator recovered that AUC within __ on average. This is a simulation under a covariate-shift assumption, not a measurement of accuracy on real unresolved candidates."
2. **Benchmark:** "On this task, FORGE reached the oracle-correct estimator in __/5 episodes vs __/5 for a single agent with the same model, tools and budget, taking __× the time (95% CI __–__) at __× the cost." If FORGE is slower or worse, that is the claim.

**Not supported, whatever the numbers:**
- accuracy on real unresolved TOIs;
- triage-time (historical) shift;
- any planet discovery or validation;
- novelty of the resolution-bias question until the Referee search is done;
- any speedup outside this task.

## 10. Open items before lock

1. **Hari:** review sections 4–7; agree γ, ρ, the threshold and the estimator set.
2. **Science lane:** `tools/tess_bias_run.py` per the contract above, with cached-snapshot loading and the γ = 0 control. Akshat can write it if that helps; data fetching is blocked in his environment, so it would be tested on a fixture.
3. **Pre-lock oracle check:** run the 6-candidate sweep once and confirm the top set holds 2 or fewer candidates.
4. **Referee search** on the resolution-bias question itself (positive-unlabeled learning, selection bias in vetting labels). This is required before any novelty wording, not before the benchmark.
5. **Adapt `bench/baseline_prompt.md`** to this task: an estimator recommendation instead of an OpenML candidate. Then freeze it with this protocol.
6. **Orchestration:** the arm B contract items in `docs/coordination/BENCHMARK.md`.

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-04 | v0.2 proposed: TESS resolution-bias instantiation | Akshat |
