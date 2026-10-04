# Benchmark review: exoplanet triage direction

- **Reviewer:** Akshat (benchmark + rigor)
- **Date:** 2026-10-04
- **Reviewed:** `docs/coordination/SCIENCE_DECISION_PACKET.md`, `tools/feasibility_exo_prior_shift.py`, `schemas/examples/exo-prior-shift-feasibility.json` (as on `main` at `e30db1a`)
- **Status:** review only. Nothing here locks the question or the protocol.
- **Verification limit:** the NASA Exoplanet Archive and the literature APIs are blocked from the environment this review was written in. Everything marked **(verify)** must be checked against the archive or the paper before it is relied on. Citations below that are not already in the decision packet are from memory and must pass `tools/citation_check.py` before they go anywhere in the submission.

## 1. Adult (Hari's earlier ask)

Agree with the science contract: the categorical-missingness comparison overlaps established work and has low breakthrough value. Keep task 7592 as the runner/engineering check only. Do not spend benchmark effort on it.

## 2. The corrected feasibility audit

The corrections are right: CANDIDATE is not a positive label, the old temporal test reused training objects, and transitions are not errors. The script now reports counts only and stores raw hashes and a retrieval timestamp. Good.

One new problem in the output:

**`koi_disposition` in the "snapshot" table is probably not a frozen snapshot (verify).** The audit shows **0** CANDIDATE → CONFIRMED transitions between `q1_q17_dr25_koi` and `cumulative`, and exactly 2,731 CONFIRMED in both. Kepler candidates have kept being confirmed since DR25 (2017), so a true snapshot comparison should show many such transitions. The likely explanation is that `koi_disposition` is the *archive* disposition, which the archive updates in place when a planet is confirmed, in every KOI table. Meanwhile `koi_pdisposition` ("disposition using Kepler data", CANDIDATE / FALSE POSITIVE only) is the pipeline output and does look frozen: it has no CONFIRMED values in either table.

Consequences:
- The 277 "transitions" on `koi_disposition` mix two processes: pipeline re-vetting and archive overlay updates. They cannot be read as "what changed after DR25".
- The confirmation date cannot come from these two tables at all. It needs a dated source: the Planetary Systems tables (`ps` / `pscomppars`) carry discovery/publication dates for confirmed planets (verify column names, e.g. `disc_pubdate`, `rowupdate`).
- Also verify what `cumulative` is: as far as I know it takes, per KOI, the disposition from the most recent delivery that dispositioned it, so it is not simply "DR25 plus later information". It contains KOIs that are not in DR25 at all (9,564 vs 8,054 rows).

## 3. Target label

Three different things are being called "the label". They must be kept apart:

| Field | What it is | Use |
|---|---|---|
| `koi_pdisposition`, `koi_score`, `koi_fpflag_*` | Kepler pipeline (Robovetter) output | **The baseline to beat**, never a feature of a model that is evaluated against FP labels, and never the truth |
| `koi_disposition` = CONFIRMED | Independent follow-up or statistical validation, published | Positive truth |
| `koi_disposition` = FALSE POSITIVE | Often set by the same pipeline flags, sometimes by follow-up | Negative truth, **with a circularity caveat** |
| CANDIDATE | Unresolved | Not a label. Censored. |

Recommendations:
1. **Positive = CONFIRMED, negative = FALSE POSITIVE, CANDIDATE excluded and counted as censored.** Report how many objects were excluded for being unresolved in every table and figure.
2. **Leakage to exclude from features:** `koi_score`, all `koi_fpflag_*`, `koi_pdisposition`, `koi_disposition` itself, `kepler_name` (it only exists for confirmed planets, so it leaks the label perfectly), `koi_vet_stat`, `koi_vet_date`, `koi_comment`, and anything from the confirmation record. Keep only quantities available at the decision time: transit fit and stellar parameters (period, depth, duration, SNR, impact parameter, planet radius, stellar Teff/logg/radius, magnitude).
3. **Circularity:** if FALSE POSITIVE labels were assigned from Robovetter flags, a model is partly being scored on agreement with the Robovetter. Report results separately for FPs with independent follow-up evidence where the archive allows it (verify which column records the FP source). At minimum, state the caveat.
4. **Selection bias is the real science here.** Confirmed planets are not a random sample of candidates. Confirmation favors bright hosts, deep transits and multi-planet systems (validation by multiplicity). The unresolved candidates are systematically harder. A model trained and tested on resolved objects is evaluated on the easy part of the population. That gap is exactly what "does triage performance transfer to the population where it's used" asks about, and it is measurable.

## 4. Cohort and split

1. **Group by host star (`kepid`), not by KOI.** Planets in the same system share stellar features, and multiplicity drives confirmation. A KOI-level split leaks across siblings. Use grouped cross-validation.
2. **The primary test should be a temporal held-out cohort**, built with a dated confirmation source:
   - Pick a cutoff date T (for example the DR25 release).
   - Training set: objects resolved (CONFIRMED with publication date before T, or FALSE POSITIVE in the DR25 pipeline output).
   - Test set: objects that were **unresolved at T and resolved after T**. This is the closest available stand-in for "the population where it's used".
   - Still-unresolved objects are censored. Their characteristics are reported but they are not scored.
3. **Describe the shift without labels.** Compare the feature distributions of the training cohort, the later-resolved test cohort, and the still-unresolved pool (SNR, depth, radius, magnitude, multiplicity). This is computable now, needs no ground truth, and shows whether the later-resolved cohort is itself a biased stand-in for the unresolved pool.
4. **Size check first (feasibility gate).** Count how many objects fall in the later-resolved test cohort before committing. If it is a few hundred or fewer, AUC confidence intervals will be around ±0.03 to 0.05, which bounds the smallest detectable effect. Set the practical threshold above that or the comparison is uninformative.
5. **Optional, a clean-truth population:** DR25 has simulated injection (true signals) and inversion/scrambling (true false alarms) sets with known truth, released for the completeness/reliability analysis (Thompson et al. 2018, already cited in the packet). They only cover instrumental false alarms, not astrophysical false positives such as eclipsing binaries, but the truth there is not circular. Worth a look as a secondary check.

## 5. Primary metric

The decision being supported is triage: ranking candidates for limited follow-up time. Recommendation:

- **Primary: ROC AUC on the temporal held-out (later-resolved) cohort, higher is better.** It is threshold-free and does not change with prevalence. That matters here because prevalence differs between cohorts by construction.
- **Derived estimand for the transfer question:** the gap = grouped-CV AUC on the training cohort minus AUC on the held-out cohort, with a bootstrap CI over host stars.
- **Secondary:**
  - Precision at a fixed follow-up budget (top-k, k stated in advance), on the held-out cohort, with that cohort's prevalence reported next to it.
  - Calibration (Brier score and calibration slope). Under prevalence shift, a model can keep its ranking but have wrong probabilities, which matters if the scores are used to set priorities across surveys.
  - Average precision (PR-AUC), with prevalence reported.
- **Practical threshold:** set after the size check in section 4, before any arm runs. Provisional: 0.02 AUC.
- **Baseline to beat:** the Robovetter disposition / `koi_score` on the same held-out cohort. If a model cannot beat the pipeline output that already exists, that is the finding.

## 6. Candidate tests (for the protocol's "two possible tests")

Two distinct first tests the Planner can choose between, both cheap:

| Test | What it measures | Cost | What changes next |
|---|---|---|---|
| T1: label-free shift audit | Feature-distribution shift between resolved, later-resolved and unresolved cohorts | Seconds, no model | Large shift → T2 is worth running and the held-out cohort needs reweighting. Small shift → the transfer question has little to find, so pivot. |
| T2: temporal transfer test | AUC gap between grouped-CV and the later-resolved cohort, against the Robovetter baseline | Minutes | Gap present → test corrections (importance weighting, recalibration). No gap → report a null transfer result. |

T1 should run first on expected learning per cost: it is nearly free, and it decides whether T2 is worth doing.

## 7. Prior art (scoped, must be verified)

The packet already cites Kopparapu et al. 2026 and Thompson et al. 2018. Closest additional work I know of, **from memory, unverified**:

- Shallue & Vanderburg 2018 (AstroNet), CNN vetting of Kepler signals.
- Armstrong, Gamper & Damoulas 2021, ML validation of Kepler candidates (about 50 newly validated planets). They apply a classifier trained on resolved objects to unresolved candidates, i.e. the deployment population, and discuss calibration.
- Valizadegan et al. 2022 (ExoMiner), validated about 300 new Kepler planets.
- McCauliff et al. 2015 (Autovetter), random-forest vetting.

**Overlap risk is high.** Armstrong et al. and ExoMiner deploy models on unresolved candidates. The residual gap, if any, is narrower: a **temporal held-out evaluation** of how vetting models trained on early-resolved objects perform on later-resolved ones, plus a quantified shift between resolved and unresolved cohorts. The Referee search has to check this exact gap before any novelty language. If it is already in those papers, the honest framing is a replication with a stricter split.

## 8. Value check (25% breakthrough potential)

Better than Adult. Follow-up time for TESS, PLATO and Roman candidates is a real bottleneck, and selection bias in training labels is a recognized open problem. But the most likely honest result is "transfer gap measured, with wide intervals", not a discovery. That is fine for the rubric if it is presented as a rigorous loop with a clear next experiment.

## 9. What the benchmark needs before freeze

1. Dated confirmation source and the size of the later-resolved cohort (section 4.4).
2. Final feature list with the leakage exclusions (section 3.2).
3. The candidate space for the oracle: models × feature sets × correction method (none, importance weighting, recalibration), evaluated on the held-out cohort.
4. Runner contract unchanged: `run(task_id, params, seed) -> {"metrics": {...}}`. For this task, `task_id` names the cohort definition.
5. Then: protocol freeze with Hari (bottleneck and denominator, primary metric, two tests and the Planner's choice rule, matched budgets, seeds, repetitions, stopping rule, uncertainty).
