# TESS target gate review (benchmark lane)

- **Owner:** Akshat
- **Date:** 2026-10-04
- **Reviewed:** the TESS candidate in `SCIENCE_DECISION_PACKET.md` and `schemas/examples/exo-target-feasibility.json` (on `main` at `aa3907f`)
- **Status:** **TESS does not clear the gate as the submission's question.** Data checks mostly pass, but the prior-art check fails. The protocol stays unlocked. No oracle, no agent comparison.
- **How checked:** web search of the archive documentation and the literature. The archive TAP API, the archive documentation pages and arXiv are blocked from this environment for direct fetches. Facts below are from search-result listings of the official pages and papers; items marked **(run)** need a query on a machine with archive access. Citations still have to pass `tools/citation_check.py` before they go in the submission.

## 1. Gate results

| Gate | Result | Basis |
|---|---|---|
| Class size | **Pass** | Audit: 1,420 KP+CP vs 1,314 FP. |
| Host disjointness | **Pass** | The archive's TOI column definitions describe `tid` as the target ID "as listed in the TESS Input Catalog (TIC)". So `tid` *is* the TIC ID, and the audit's caveat "the TOI table exposes no TIC column" can be dropped. Grouping on `tid` is star-level grouping. |
| Independent reference, positives | **Feasible, not yet run** | `ps` and `pscomppars` both carry `tic_id`, so `tid` → `pscomppars.tic_id` gives a published-confirmation cross-match. **(run)** Report the match rate for CP and for KP separately. |
| Independent reference, negatives | **Partial** | TFOPWG false positives are typically set from ground-based follow-up: seeing-limited photometry that finds a nearby eclipsing binary (SG1), or large RV variation. That evidence is outside the TESS transit parameters, so the Kepler circularity objection is weaker here. But the archive holds no per-object record of *why* a TOI was dispositioned FP. ExoFOP-TESS notes are the only source. |
| Prospective temporal split | **Weak** | The TOI table has `toi_created` but, as far as the column definitions show, no date when a disposition was assigned. **(run: confirm)** A split on creation date can't tell when a label became known, and recent TOIs that are already resolved are biased toward the quick, easy cases. |
| Prior art | **Fail** for plain classification | See section 2. |

Two label details to settle whatever the question ends up being:
- **KP** means "known planet from a previous survey". Its label comes from a catalog lookup, not TESS vetting, and it is dominated by easy giant planets. Report KP and CP separately, or exclude KP.
- **FA** (false alarm) is a resolved non-planet but is currently censored with PC/APC. Decide explicitly whether it counts as a negative.

## 2. Prior art: TESS confirmed-vs-false-positive classification is already published

Closest work found (search listings; still to be checked with `citation_check.py`):

| Work | What it already does |
|---|---|
| Kopparapu et al. 2026, AJ 172, 100; arXiv:2606.07769 | **Nearly our exact design:** MLP/RF/XGB on balanced confirmed planets vs false positives from **TESS and Kepler**, using six catalog parameters (period, radius, Teff, stellar radius, depth, duration), with cross-instrument train/test. Notes that resolved candidates had "characteristics amenable to classification". |
| Yu et al. 2019, AJ, doi:10.3847/1538-3881/ab21d6 | Automated triage and vetting of TESS candidates (Astronet-Triage/Vetting). |
| Osborn et al. 2020, A&A 633, A53 | CNN classification of TESS planet candidates. |
| Tey et al. 2023, arXiv:2301.01371 | Improved TESS full-frame-image light-curve classification. |
| ExoMiner++ (2025), arXiv:2502.09790 | TESS vetting with Kepler-to-TESS transfer learning, plus a vetting catalog. |
| ExoNet (2026), arXiv:2604.15560 | Calibrated multimodal TESS candidate vetting. |
| Armstrong et al. 2021, MNRAS 504, 5327 | ML validation of Kepler candidates (50 new planets). |
| Valizadegan et al. 2022 (ExoMiner), ApJ 926, 120, doi:10.3847/1538-4357/ac4399 | Kepler vetting and validation of 301 planets. |
| Shallue & Vanderburg 2018, AJ 155, 94, doi:10.3847/1538-3881/aa9e09 | CNN vetting of Kepler signals. |

Plain TESS KP/CP vs FP classification, and Kepler-to-TESS transfer, are therefore **KNOWN**. Presenting either as the submission's question would overlap a 2026 refereed paper.

## 3. Blocker

The TESS target is technically usable (class sizes, host key, censoring rule), but the question it supports is already answered in the literature. The reference standard is also asymmetric: positives can be checked against publications, negatives only against TFOPWG judgments.

## 4. Suggested next candidate

### Recommended: resolution-bias audit on TESS

> On TESS TOIs, does a vetting model's accuracy measured on resolved objects (KP/CP vs FP) overstate its accuracy on the unresolved candidates (PC/APC) it is actually used to triage?

Why this one:
- It is the residual gap. Kopparapu et al. note the bias in passing; quantifying it was not found in our search, and neither was positive-unlabeled learning applied to exoplanet vetting. That is "not found in this search", not proof of novelty, and the Referee must search again.
- It reuses everything already built: the TOI pull, the censoring rule, `tid` grouping. It runs in seconds on tabular features.
- It has a real decision consequence: whether resolved-set accuracy can be quoted as triage accuracy when follow-up time is allocated.

Two first tests for the Planner:

| Test | What it does | Result → next decision |
|---|---|---|
| T1: shift test (label-free) | Train a classifier to tell resolved from unresolved TOIs on the same features, with `tid`-grouped CV. AUC with a CI. | CI includes 0.5 → no detectable shift; the bias question is closed (falsifier). AUC clearly > 0.5 → run T2. |
| T2: corrected estimate | Importance-weighted AUC estimate for the unresolved pool vs the naive resolved AUC, plus a positive-unlabeled estimate of the planet fraction among PC/APC. | A large gap means resolved-set accuracy overstates triage accuracy → recommend reweighting before follow-up ranking. |

T1 goes first: it is nearly free and decides whether T2 is worth running.

**Limit:** the unresolved pool has no ground truth, so T2 is an estimate under a stated assumption (shift explained by the features), not a measurement.

**Benchmark oracle:** score correctness on a **semi-synthetic** version where truth is known. Hide labels on the resolved set with a feature-dependent probability matched to the shift that T1 measures. The "correct" answer is then which correction method recovers the true held-out AUC. That gives a deterministic oracle without pretending to know the truth for the unresolved pool.

### Fallback

If Hari's prior-art search finds this already quantified, close astronomy and reopen the shortlist outside it, following `SCIENCE_QUESTION_RESEARCH_PLAN.md`. Do not fall back to Kepler false positives or plain TESS classification.

## 5. Next actions

1. **Hari (run):** `tid` → `pscomppars.tic_id` cross-match rate (CP and KP separately); confirm there is no disposition-date column; decide KP and FA handling.
2. **Hari:** Referee search on the exact resolution-bias question, including positive-unlabeled learning and selection bias in vetting labels.
3. **Akshat:** once the question is chosen, draft the protocol for the T1/T2 design and the semi-synthetic oracle. Freeze only jointly with Hari.
