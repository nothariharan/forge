# Science decision packet: exoplanet direction under review

**Owner:** Hari (science lead)
**Prepared:** 2026-10-04
**Status:** **Interim direction only; research question and benchmark are not locked. The original classifier precision result is invalidated.**
**Next gate:** Akshat reviews the target, cohort, and metric after the science lead resolves them.
**Rubric:** `docs/references/reference-02.pdf`, Track 03, pages 2–4.

## Decision for team coordination

Use **astronomy / exoplanet-catalog vetting** as the provisional domain for the product story. Do not yet claim the team has a validated exoplanet triage question, a measured precision-transfer gap, a discovery, or a performance result.

The current NASA archive feasibility run is now classified as a **catalog disposition audit only**. Its previous classifier results and “planet-positive rate” interpretation are withdrawn. The new raw audit is [`schemas/examples/exo-prior-shift-feasibility.json`](../../schemas/examples/exo-prior-shift-feasibility.json); it reports status counts and snapshot transitions, no model metrics.

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

## Candidate scientific direction, still unresolved

A defensible follow-up must first choose an outcome that is actually observed and a cohort with independent held-out objects. Possible directions to investigate, not approved hypotheses:

- **Retrospective triage among later-resolved objects:** define a historical cohort of candidates with subsequent independently recorded confirmed-planet or false-positive outcomes; train on disjoint objects and evaluate only the held-out, later-resolved cohort. Ongoing candidates are censored/unknown, not positives.
- **Disposition instability:** ask whether measurable, predeclared catalog features predict later disposition revision between two fixed releases. This studies status changes, not true planet classification; check for direct prior work and possible archive-process artifacts.
- **Kepler-to-TESS transfer:** only consider this after reviewing the 2026 instrument-agnostic prioritization paper and precisely defining label compatibility, feature availability, and a leakage-safe external test.

The leading option is not selected until we establish reliable outcome labels, object-disjoint training/evaluation cohorts, available dates/snapshots, practical utility, and a prior-art gap. If none survives those checks, reopen the domain shortlist rather than forcing the original claim.

## Handoff so other work can proceed safely

- **Science (Hari):** own outcome/estimand definition, referee search, and corrected preregistration. Do not publish classifier metrics until a valid labeled holdout exists.
- **Benchmark (Akshat):** review the estimand, target-label semantics, independent split, and primary metric; then freeze the protocol with science. Do not build the oracle around the old 90.5% or old “temporal” scores.
- **UI (Saksham / UI contributor):** the room/workflow UI may use the provisional astronomy context and generic replay events. Show source provenance, catalog status labels, hypotheses, test choice, approval, result, and replanning. Keep statuses named CANDIDATE / CONFIRMED / FALSE POSITIVE / UNKNOWN; do not display candidate fraction as planet precision. Label fake event content as demo data. Do not require a model score until the scientific target is approved.
- **Core/CLI (Ish):** retain the shared event schema and generic event replay; no science-specific schema change is needed yet.
- **Orchestration (Saksham):** keep the Omnigent workflow visible as the agent runtime/policy layer. Any scientific result shown in a live run must have provenance and a preregistered metric.

The existing `schemas/examples/sample-run.jsonl` is fabricated Adult demo data, not an exoplanet result. It may be used to build generic layout/replay behavior if labeled clearly; it should not be presented as astronomy evidence.

## Lock gate

Before freezing the science contract or starting the oracle/A-vs-B benchmark, record:

1. Exact research question and domain-reviewed decision consequence.
2. Outcome definition, adjudication/reference source, and how unknown/censored objects are handled.
3. Dataset table/version and snapshot dates; feature availability at the decision time.
4. Object-disjoint split and leakage checks.
5. Baseline, candidate interventions, primary metric/direction, practical threshold, and uncertainty plan.
6. At least two possible tests and why the first is best by expected learning, feasibility, and cost.
7. Scoped prior-art query log including NASA completeness/reliability work and the 2026 instrument-agnostic paper.
8. A reproducible smoke result with raw output, code/data hashes, runtime, and setup details.

Until then, the science choice and benchmark protocol remain **not locked**. No current result supports a planet-precision, novelty, discovery, or acceleration claim.
