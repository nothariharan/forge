# Science decision packet: exoplanet direction under review

**Owner:** Hari (science lead)
**Prepared:** 2026-10-04
**Status:** **Target resolution decided: the Kepler planet-outcome target is CLOSED, with measurements. One exoplanet candidate survives (TESS TOI resolved dispositions) but is NOT locked and still has an open independent-reference-standard gate. The benchmark protocol stays unlocked.**
**Next gate:** the science lead and Akshat jointly review the surviving TESS target and its open gate, or reopen the domain shortlist.
**Rubric:** `docs/references/reference-02.pdf`, Track 03, pages 2–4.

## Decision for team coordination

Use **astronomy / exoplanet-catalog vetting** as the provisional domain for the product story. Do not yet claim the team has a validated exoplanet triage question, a measured precision-transfer gap, a discovery, or a performance result.

The current NASA archive feasibility run is now classified as a **catalog disposition audit only**. Its previous classifier results and “planet-positive rate” interpretation are withdrawn. The new raw audit is [`schemas/examples/exo-prior-shift-feasibility.json`](../../schemas/examples/exo-prior-shift-feasibility.json); it reports status counts and snapshot transitions, no model metrics.

## Target resolution (2026-10-04): Kepler is closed as a planet-outcome target

The task was to choose an outcome the archive actually observes, define censoring, and guarantee object-disjoint train/evaluation objects. That work is done, and it produced a negative result for the whole Kepler direction. Reproduce with:

```powershell
py -3.12 -X utf8 tools/audit_exo_target_feasibility.py --output schemas/examples/exo-target-feasibility.json
```

Raw artifact: [`schemas/examples/exo-target-feasibility.json`](../../schemas/examples/exo-target-feasibility.json), which stores the retrieval timestamp and SHA-256 of every raw TAP response.

### 1. Censoring rule is now fixed

`CANDIDATE` and `NOT DISPOSITIONED` are **unresolved**. They are censored: excluded from the labeled cohort and reported separately. They are never recoded as positives. This is the specific step the withdrawn analysis got wrong.

An outcome is observable only at a **later** release than the one supplying features. Objects already labeled at the feature release are excluded from the cohort by construction, so no training object can appear in its own evaluation cohort.

### 2. The confirmed-planet class is effectively frozen

CONFIRMED count by release: Q1-Q6 **1949**, Q1-Q8 **2320**, Q1-Q12 **2693**, Q1-Q16 **2735**, DR24 **2714**, DR25 **2731**, CUMULATIVE **2748**.

After Q1-Q16 the net change is **+13 objects (+0.48%)** while the catalog grew **+30.2%**. The confirmed share fell from **37.2%** to **28.7%**. CONFIRMED is a near-absorbing state: later releases revise false positives, they do not manufacture planets.

### 3. Every unresolved-to-resolved cohort is too small

| Cohort (unresolved at t0 → release at t1) | CONFIRMED | FALSE POSITIVE | Censored | Feasible |
|---|---:|---:|---:|:--:|
| Q1-Q16 `NOT DISPOSITIONED` → DR24 | **28** | 1132 | 759 | No |
| Q1-Q16 `CANDIDATE` → DR24 | **14** | 34 | 403 | No |
| DR24 `CANDIDATE` → DR25 | **4** | 440 | 1018 | No |
| DR25 `CANDIDATE` → CUMULATIVE (2026) | **0** | 129 | 1229 | No |

The gate used is a stated minimum usable class of **200** per class. The largest confirmed class available anywhere in the Kepler disposition history is **28** objects. A prospective confirmed-planet experiment cannot be run, reported, or reviewed on Kepler. This also independently explains why the withdrawn 90.5% figure was meaningless: it was counting “still unresolved,” not planets.

### 4. Join hazard found and fixed

`kepoi_name` is **not stable across deliveries**. A strict Q1-Q16 → DR24 join silently drops 1356 of 7348 rows, including 27 objects that were later promoted to CONFIRMED — that is, the rarest and most decision-relevant class. The audit therefore reports two tiers (strict `kepoi_name`, then `kepid` fallback), counts ambiguity explicitly, and excludes ambiguous multi-KOI systems rather than assigning them. Any future exoplanet protocol must use the same two-tier join and must not report a strict-join-only cohort.

### 5. Kepler false-positive target is not recommended

FALSE POSITIVE is abundant (3965 in DR25) and adjudicated, so it survives the class-size gate. It is still rejected on scientific grounds: the disposition was produced by the Kepler vetting pipeline from the same photometric and astrometric quantities the candidate features encode, including the documented `koi_fpflag_nt/ss/co/ec` rules. A model trained on it would largely **distill the archive’s own vetting decisions**. That is a reproducibility check, not a scientific hypothesis test, and should not be presented as the submission’s question.

## The one surviving exoplanet candidate: TESS resolved dispositions

| Quantity | Value |
|---|---:|
| TOI rows | 8148 |
| Positive, `KP` + `CP` | **1420** |
| Negative, `FP` | **1314** |
| Censored, `PC` + `APC` + `FA` | 5400 |
| Blank disposition | 14 |
| Usable labeled cohort | **2734** (51.9% positive) |
| Distinct hosts (`tid`) in cohort | 2588 |
| Hosts with >1 resolved TOI | **109** |
| `toi_created` populated | 8148 / 8148, range 2018-08-30 → 2026-08-27 |

This passes the class-size gate with a near-balanced target, the censoring rule transfers unchanged, and the outcome class is genuinely replenished as the mission runs — the failure that ended the Kepler direction.

**Disjointness control:** the TOI table has **no TIC column**. `tid` (TESS object) is the only host grouping key, and 109 hosts carry more than one resolved TOI, so a random row-level split would leak across the same star. Split on `tid`.

**Open gate — this candidate is not locked.** `ctoi_alias` turned out **not** to be an independent reference standard: it is populated for all 2734 resolved rows, including all 1314 false positives. So the archive does not currently offer, in this table, a confirmation signal that is independent of `tfopwg_disp`. Until one of the following is demonstrated, the same circularity objection that retires Kepler FP also applies here:

1. An independent adjudication source for `KP`/`CP` — for example a cross-match against `pscomppars` or ground-based confirmation records — with the cross-match rate reported.
2. A prior-art review. Kopparapu et al. (2026) already evaluate Kepler/TESS train/test combinations, so plain TESS candidate classification likely overlaps prior work.
3. A prospective temporal split on `toi_created` where the confirmed class still grows after the cut date.
4. A `tid` → TIC cross-check so host-level disjointness is verified, not assumed.

If (1) fails, close the exoplanet domain and reopen the shortlist outside astronomy. **Do not fall back to the Kepler false-positive target.**

## Limits of this resolution

This is a label-availability audit. It is not a scientific result, a novelty claim, a benchmark result, or evidence that any model works. Dispositions are the archive’s own best-knowledge automated and committee adjudications, not ground truth. Archive contents change; compare reruns using the stored timestamps and hashes. The previously withdrawn exoplanet classifier figures remain withdrawn.

## Why the original question is not ready

The first draft asked whether precision measured on dispositioned objects transfers to unresolved candidates. Its implementation did not measure that:

1. NASA defines a **CANDIDATE** as a possible planet that has passed the tests so far; it is not a confirmed-planet outcome. A candidate can later be reclassified. Therefore the old 90.5% figure was “still labeled CANDIDATE among this historical cohort,” not planet prevalence or classifier precision. See [NASA KOI disposition definitions](https://exoplanetarchive.ipac.caltech.edu/docs/API_kepcandidate_columns.html).
2. The old “temporal” code trained a classifier on DR25 rows, then predicted on those same object rows and compared to the current status. That reuses the training objects and is not an independent temporal holdout.
3. The objects still marked CANDIDATE have no final positive/negative truth label in this table. Their true PPV cannot be computed from the current unresolved pool. Counting them as positives assumes the outcome that the proposed triage system is supposed to predict.
4. “Disposition changed” is a catalog transition, not necessarily an error. The archive explicitly describes the DR25 KOI catalog as automated vetting and a best-knowledge catalog, while dispositions can be updated with additional evidence. Do not call flips a measured false-negative rate without a defined reference standard.
5. Prior art is closer than the first search suggested. Kopparapu et al. (2026) evaluate eleven ML models using confirmed-planet and false-positive labels and Kepler/TESS train/test combinations, and discuss extending candidate prioritization to Roman ([The Astronomical Journal paper](https://doi.org/10.3847/1538-3881/ae7d0f), [arXiv version](https://arxiv.org/abs/2606.07769)). Kepler DR25 also has extensive completeness and reliability analyses, including simulated injections and false-positive/reliability products ([Thompson et al., DR25 catalog](https://arxiv.org/abs/1710.06758), [NASA archive products](https://exoplanetarchive.ipac.caltech.edu/docs/Kepler_completeness_reliability.html)). A domain-aware prior-art review is required before asserting a gap.

## What the corrected feasibility audit establishes

The script `tools/feasibility_exo_prior_shift.py` now fetches and counts dispositions in `q1_q17_dr25_koi` and `cumulative`, joins by KOI identifier, and records transitions. It does not train a model or compute precision.

Observed in the 2026-10-04 retrieval:

- DR25 snapshot: 8,054 rows; 1,358 CANDIDATE, 2,731 CONFIRMED, 3,965 FALSE POSITIVE.
- Current cumulative table: 9,564 rows; 1,977 CANDIDATE, 2,748 CONFIRMED, 4,839 FALSE POSITIVE.
- Among the 1,358 DR25 candidates in the join: 1,229 are currently still labeled CANDIDATE and 129 are now FALSE POSITIVE. None of these two statuses supplies confirmed-planet truth for the cohort.
- Across 8,054 common KOIs, 277 disposition transitions appear in the all-row join. An earlier 274 figure came from a complete-feature subset and is not the all-row transition count. Transitions are status revisions, not independently adjudicated errors.

These values demonstrate accessible versioned catalog tables and nonzero disposition changes. They do **not** demonstrate a 3.5× true base-rate gap, a classifier precision gap, or a deployment-population transfer failure.

Reproduce the data audit with:

```powershell
py -3.12 -X utf8 tools/feasibility_exo_prior_shift.py --output schemas/examples/exo-prior-shift-feasibility.json
```

The artifact stores its retrieval timestamp and SHA-256 hashes of both raw TAP CSV responses. Archive contents can change; use the stored hashes and timestamp when comparing reruns.

## Candidate scientific direction, narrowed by the target resolution

The measurements above retire the first two options below on evidence, not preference. Retained here for the record:

- ~~**Retrospective triage among later-resolved Kepler objects.**~~ **Retired by measurement.** Every such cohort was enumerated; the largest confirmed class is 28 objects. See the cohort table above.
- ~~**Disposition instability.**~~ **Retired by measurement.** The revision class that would serve as the outcome is 129 objects at best, and the target would be a catalog-process artifact rather than a planet outcome.
- **Kepler false-positive prediction.** **Rejected on circularity**, not on class size. Predicting `FALSE POSITIVE` from photometric and astrometric features reproduces the vetting pipeline’s own documented rules.
- **TESS resolved dispositions (`KP`/`CP` vs `FP`).** The only survivor. Class sizes and censoring are settled; the independent-reference-standard gate is open.
- **Kepler-to-TESS transfer.** Keep on the list as a reframing of the survivor if the reference-standard gate closes: harmonized features, a leakage-safe external test on TESS hosts disjoint from Kepler training hosts, and label compatibility stated precisely. Only after reviewing the 2026 instrument-agnostic prioritization paper.

The leading option is not selected until the TESS reference-standard gate closes and the prior-art review is done. If it does not close, reopen the domain shortlist outside astronomy rather than forcing any exoplanet target.

## Handoff so other work can proceed safely

- **Science (Hari):** resolve the TESS independent-reference-standard gate (try the `pscomppars` cross-match and report the rate), then run the prior-art review. Do not publish classifier metrics until that gate closes.
- **Benchmark (Akshat):** the estimand is now specified well enough to draft against — outcome `KP`/`CP` vs `FP`, censoring `PC`/`APC`/`FA`, host-disjoint split on `tid` — but the target is **not locked**. Do not freeze the protocol, do not build the oracle, and do not reuse the withdrawn 90.5% or the old “temporal” scores.
- **UI (Saksham / UI contributor):** the room/workflow UI may use the provisional astronomy context and generic replay events. Show source provenance, catalog status labels, hypotheses, test choice, approval, result, and replanning. Keep statuses named CANDIDATE / CONFIRMED / FALSE POSITIVE / UNKNOWN; do not display candidate fraction as planet precision. Label fake event content as demo data. Do not require a model score until the scientific target is approved.
- **Core/CLI (Ish):** retain the shared event schema and generic event replay; no science-specific schema change is needed yet.
- **Orchestration (Saksham):** keep the Omnigent workflow visible as the agent runtime/policy layer. Any scientific result shown in a live run must have provenance and a preregistered metric.

The existing `schemas/examples/sample-run.jsonl` is fabricated Adult demo data, not an exoplanet result. It may be used to build generic layout/replay behavior if labeled clearly; it should not be presented as astronomy evidence.

## Lock gate

Item 2 is now partially satisfied for TESS (outcome definition and censoring are fixed) and item 4 is specified (host-disjoint split on `tid`). Still required before freezing:

1. Exact research question and domain-reviewed decision consequence.
2. **Open:** an independent adjudication/reference source for `KP`/`CP`, with cross-match rate. `ctoi_alias` does not qualify.
3. Dataset table/version and snapshot dates; feature availability at the decision time.
4. **Open:** verify `tid` → TIC host disjointness rather than assuming it.
5. Baseline, candidate interventions, primary metric/direction, practical threshold, and uncertainty plan.
6. At least two possible tests and why the first is best by expected learning, feasibility, and cost.
7. Scoped prior-art query log including NASA completeness/reliability work and the 2026 instrument-agnostic paper.
8. A reproducible smoke result with raw output, code/data hashes, runtime, and setup details.

Until then, the science choice and benchmark protocol remain **not locked**. No current result supports a planet-precision, novelty, discovery, or acceleration claim.
