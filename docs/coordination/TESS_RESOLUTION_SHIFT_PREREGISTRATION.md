# Preregistration: T1 resolution-shift smoke test on TESS TOIs

**Owner:** Hari (science lead)
**Date:** 2026-10-04
**Status:** **EXECUTED. The current-catalog fields distinguish resolved from unresolved TOIs in this run. This is not evidence that those fields were available at triage, not an accuracy-gap result, not a science claim, and not benchmark evidence. T2 remains conditional on feature-provenance and prior-art review.**
**Authority:** [`SCIENCE_DECISION_PACKET.md`](SCIENCE_DECISION_PACKET.md) lock-gate items; [`BENCHMARK_TESS_GATE_REVIEW.md`](BENCHMARK_TESS_GATE_REVIEW.md) section 4 test T1.

## Why this test

The TESS plain-classification target **failed the prior-art gate**. The residual candidate question is whether a vetting model's accuracy measured on resolved objects overstates its accuracy on the unresolved candidates it is actually used to triage.

T1 is a cheap descriptive check. It does not measure vetting accuracy. It tests whether current catalog values distinguish resolved from unresolved objects. The archive does not provide historical feature values at disposition time, so T1 cannot establish that these values were available at triage. A shift in current values alone neither proves nor rules out an accuracy gap.

## Question

In the current NASA Exoplanet Archive TESS Objects of Interest table, can a classifier distinguish **resolved** from **unresolved** objects using the available photometric and ephemeris columns?

## Population and labels

- Source: `toi` table, all rows with a non-blank `tfopwg_disp`.
- **Resolved** = `{CP, FP}`. `KP` is excluded because its label is a previous-survey catalog lookup rather than TESS-side adjudication. `FA` is excluded from the primary arm because its host-match rate behaves like `FP`; it is tested as a sensitivity arm.
- **Unresolved** = `{PC, APC}`.
- `tid` is the grouping key. It is the TIC ID and one host can carry several TOIs, so a row-level split would leak across stars.

## Features

Numeric `pl_*` and `st_*` columns. Excluded by name, with reason:

| Excluded | Reason |
|---|---|
| `tfopwg_disp` | the label |
| `toi`, `tid`, `toipfx` | identifiers / label proxy |
| `toi_created`, `rowupdate`, `release_date` | timestamps; older TOIs are mechanically likelier to be resolved, so including them detects resolution age rather than triage-relevant shift |
| `*_symerr`, `*_lim` | asymmetric-error and detection-limit derivations, not independent measurements |

Primary arm excludes timestamps. A sensitivity arm adds them, to show how much of any detected shift is resolution age.

## Method

- Model: logistic regression, `max_iter=2000`, median imputation, standardization. Chosen for determinism and speed, not for performance.
- Split: `GroupKFold` on `tid`, 5 folds, `shuffle=True`, seeds `{0, 1, 2, 3, 4}`.
- Primary metric: out-of-fold ROC AUC for resolved vs unresolved, **direction: above 0.5 means detectable shift**.
- Uncertainty: 2000-iteration bootstrap over `tid` clusters on the out-of-fold predictions, 95% percentile interval.
- Null control: labels permuted within the same grouped folds, 200 permutations, to confirm the pipeline does not manufacture AUC on its own.

## Prediction

Out-of-fold AUC is **greater than 0.5**, and the 95% bootstrap interval **excludes 0.5**.

## Planned decision rule

An upper 95% bootstrap bound **below 0.5** would support separation in the opposite direction and contradict the preregistered prediction that AUC exceeds 0.5. If the interval overlaps 0.5, the result is inconclusive; it does not establish exchangeability or rule out an accuracy gap.

## Stopping rule

Stop after the primary arm and the two sensitivity arms. Do not add models, feature engineering, or per-arm tuning after seeing results. If the primary arm is inconclusive in either direction, report it as inconclusive rather than re-running with a different model.

## What this is not

- Not benchmark evidence. No agent arm, no A-vs-B comparison, no oracle.
- Not a claim about planet vetting accuracy. T1 never trains a planet classifier.
- Not a novelty claim. The resolution-bias question still needs a Referee search; "not found in our search" is not proof.
- Not a substitute for the open lock gate. Passing T1 does not lock the science contract.

## Recorded run

Command:

```powershell
py -3.12 -X utf8 tools/tess_resolution_shift.py --output schemas/examples/tess-resolution-shift.json
```

Raw artifact: [`schemas/examples/tess-resolution-shift.json`](../../schemas/examples/tess-resolution-shift.json). Environment: Python 3.12.10, NumPy 2.5.1, scikit-learn 1.9.0. Data hash and retrieval timestamp are in the artifact. Runtime ~24 s per arm, ~50 s including the permutation control.

Cohort: 7427 rows, 7143 hosts, 39 features after excluding label/identifier/timestamp/derivation columns and dropping 4 all-missing columns. Cell missingness 3.9%. Class balance 2127 resolved / 5300 unresolved. Dropped by state as preregistered: `KP` 607, `FA` 100, blank 14. 223 hosts carry more than one TOI, which is why grouping is on `tid`.

| Arm | OOF AUC | 95% cluster-bootstrap CI | Verdict |
|---|---:|---|---|
| Primary: `{CP,FP}` vs `{PC,APC}` | **0.7616** | **[0.7492, 0.7737]** | prediction supported, falsifier not triggered |
| Sensitivity: + numeric timestamp offsets | 0.7992 | [0.7878, 0.8112] | same conclusion |
| Sensitivity: `FA` counted as resolved | 0.7655 | [0.7541, 0.7769] | same conclusion |

Per-seed primary AUCs: 0.7615, 0.7595, 0.7603, 0.7604, 0.7627.

Permutation control: mean **0.4973**, p95 0.5144, max 0.5257 over 200 permutations. The pipeline does not manufacture AUC, and the observed 0.7616 is far outside the null.

### Reading of the result

The prediction was that out-of-fold AUC exceeds 0.5 with an interval excluding 0.5. That holds for the current catalog values. However, the table does not establish these fields' availability at original disposition time. This is current-snapshot separability, not a measured triage-time covariate shift and not an accuracy-gap result. T2 is not approved by this result alone.

Two qualifications that must travel with this number:

1. **Timestamps add 0.038 AUC** (0.7616 → 0.7992) in the current snapshot. This does not resolve whether non-timestamp fields were updated after disposition.
2. **Shift is not an accuracy gap.** A detectable difference in current catalog values neither measures nor guarantees an accuracy difference. Do not quote 0.76 as an accuracy overstatement.

### Post-run methodological clarification (2026-10-04)

The initial preregistration draft said that an interval including 0.5 would establish no shift and exchangeability. That inference is not justified: overlap with 0.5 is inconclusive, not evidence of equivalence. This clarification does not change the recorded result because the observed interval is wholly above 0.5. The current table also lacks historical feature values at disposition time, so the run must be described as current-catalog separability only. Neither this result nor a semi-synthetic follow-up establishes real unresolved-pool accuracy without additional assumptions and validation.

### Deviations and bugs found before the recorded run

- The first execution of the sensitivity arm returned an AUC identical to the primary arm. Cause: the timestamp columns are strings, so they parsed to all-NaN and the arm measured nothing. They are now converted to numeric day offsets before the arm runs. The corrected arm is the 0.7992 row above.
- The exclusion rule for derived columns was written as `_lim` / `_symerr`, but the archive names these columns `pl_eqtlim`, `pl_insolsymerr`, `st_distlim` and so on. The rule never fired, so limit and asymmetric-error columns were being fed in despite the preregistration. The rule now matches `lim` / `symerr`, which drops the feature set from 63 to 39. **The primary AUC is unchanged at 0.7616**, because those columns were all-missing or constant for this cohort.
- The falsifier requires the entire interval below 0.5, so under a true null it still fires about 2.5% of the time. The permutation control, not the point estimate, is what establishes the pipeline is sound.
