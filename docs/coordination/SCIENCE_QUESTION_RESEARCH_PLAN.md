# Research sprint: choose FORGE's science question

**Owner:** Hari (science lead)
**Status:** Ready to execute; question not selected
**Target:** Return a decision-ready shortlist before protocol freeze with Akshat.
**Challenge source:** `docs/references/reference-02.pdf`, Track 03, 7th Global AI Hackathon.

## Objective

Select one important, narrow scientific question that FORGE can investigate with accessible literature and data, run a reproducible computational experiment for, and use the result to justify a different or more specific next decision.

Do not select a question because it makes a good-looking dashboard. Select a real question whose workflow the UI can make understandable. The UI can then show evidence, competing hypotheses/tests, preregistration, the run, result, policy/human gate, and replan.

The brief requires Omnigent to orchestrate live specialist agents. It asks for at least two possible tests, a reasoned choice using expected learning, feasibility and cost, and a complete loop from question through updated decision. The 10x goal is a moonshot: report measured progress against a defined bottleneck, not a promised speedup. See PDF pages 2–4.

## Current exclusion / known candidate

OpenML Adult task 7592 is a proven engineering/runner check, not the default science choice. The basic categorical-imputation/model comparison and an Adult fairness extension have prior work in the science contract. Do not present the current question or seed-1 sweep as novel discovery. Reconsider Adult only if the search finds a precise, consequential gap that can be tested within the available time.

## Sprint sequence

### 1. Set hard constraints

Write down the actual time remaining until the submission deadline; compute/data limits; available API and model access; domains the team can explain; and whether the result must run offline in the demo. Reject ideas that depend on unavailable credentials, new data collection, expensive hardware, wet-lab work, or a full literature review.

### 2. Generate a broad but bounded longlist

Draft 5–8 candidate questions across at least three areas the team can execute (for example: AI/ML behavior, climate/energy, or biomedical/public-health datasets). Keep each to one sentence and make its outcome computable from existing data, a simulation, or a benchmark.

Use this question form:

> On **[named dataset/system and population]**, does **[specific intervention or condition]** change **[predeclared measurable outcome]** relative to **[baseline]**, under **[fixed split/control]**?

For each candidate add: why a domain expert should care; the expected scientific decision if the result is positive, null, or contrary; the likely dataset/source; and the smallest possible feasibility run.

Avoid vague goals such as “find a breakthrough with AI,” open-ended model comparisons, and questions whose only contribution is trying several standard algorithms on a familiar dataset.

### 3. Screen prior work before coding

For each longlist candidate:

- Search the exact question, target population/system, intervention, dataset, and outcome separately. Search synonyms and cited-by/review literature.
- Prefer primary studies, benchmark papers, dataset/task documentation, and official repositories. Record search services, exact queries, date, and coverage.
- Find the closest 3–5 prior works. For each, record what they tested, data, outcome, and the specific unresolved piece (if any).
- Ask: would a competent reviewer say the proposed result is already in a table/figure, a direct re-run, or an expected consequence of established work? If yes, reject or narrow it.
- Label novelty only as “not found in this search,” “overlaps prior work,” or “uncertain.” A search cannot prove novelty.

### 4. Check data and execution feasibility

For the best 2–3 candidates, locate the exact dataset/task and verify from its primary source:

- stable URL/ID, version/snapshot, license and access method;
- row/record count, target and feature availability, missingness/quality issues;
- train/test or official split, leakage risks, and metric already specified by the task;
- baseline and at least two genuinely distinct tests/interventions;
- runtime and cost for one minimal run in the available environment;
- what would count as a useful effect, null result, or falsifier.

Run the smallest smoke test that can rule out a dead end. Save raw output and exact command. Do not spend time on a full sweep until the question and comparison have passed screening.

### 5. Score and choose

Score each remaining candidate 1–5. Add one sentence of evidence for each score.

| Criterion | Weight | What a high score means |
|---|---:|---|
| Importance | 25% | A real scientific or practical decision could change |
| Specific gap after prior-art search | 25% | The exact question is not already answered by the closest work |
| Testability and falsifiability | 20% | A small, reproducible computation can distinguish alternatives |
| Evidence and reproducibility | 15% | Data, controls, metrics and raw artifacts are accessible |
| FORGE/demo fit | 10% | The question naturally demonstrates evidence → prediction → experiment → replan and Omnigent coordination |
| Cost and deadline fit | 5% | A meaningful run and analysis fit available time and resources |

**Hard gates:** do not select a candidate with inaccessible/unlicensed data, no credible baseline, no measurable outcome, a direct prior-art duplicate, or no plausible result-driven next decision. Prefer a lower score with clear evidence over optimistic assumptions. A score helps compare options; it is not proof of scientific merit.

### 6. Return a decision packet

Bring back one folder or a single document containing:

1. **Ranked shortlist:** top 2–3 candidates, score table, and reject reasons for the rest.
2. **Recommended question:** exact one-sentence wording and why it matters.
3. **Prior-art table:** 3–5 closest sources per finalist, with working links/DOIs/arXiv IDs, source type, what each established, and the residual gap. Include query log and search date.
4. **Dataset card:** official ID/URL, version, license, target, size, split, access/API constraints, and known caveats.
5. **Experiment sketch:** baseline plus at least two tests; independent/dependent variables; controls; primary metric and direction; practical threshold; seed/repetition plan; falsifier; estimated runtime/cost.
6. **Expected-learning choice:** why one test should run first using expected learning, feasibility and cost; what outcomes change the next test.
7. **Minimal smoke-run artifact:** exact command, environment, raw stdout/JSON, runtime, any setup issue, and a data/code hash if practical. Label it feasibility-only.
8. **Risk and limits:** confounding, leakage, small sample, subgroup/ethics concerns, compute, uncertainty, prior-art uncertainty, and what would still need expert or real-world validation.

### 7. Pause for joint lock with benchmark

Do not start the full oracle sweep or A-vs-B agent benchmark from a shortlist. Once Hari selects a science candidate, review it with Akshat and freeze the question, metric/direction, threshold, candidate space, splits, seeds, budget, primary benchmark outcome, baseline prompt, stopping rule, and analysis before comparative runs.

## Copyable research task prompt

> Help select FORGE’s scientific question for Track 03 Agentic Scientific Discovery. Read `docs/references/reference-02.pdf`, `docs/coordination/SCIENCE_CONTRACT.md`, and this plan first. Generate 5–8 narrow, testable candidate questions across at least three feasible domains. Screen each against primary literature and official dataset documentation; do not call a question novel just because a quick search found nothing. Reject the existing Adult categorical-imputation question as a breakthrough claim unless you identify a specific unaddressed gap. Rank the best 2–3 candidates using the weighted scorecard in this plan, with evidence for every score. For finalists, verify dataset/task ID, version, license, split, target, metric, access and one-run cost/runtime. Propose at least two distinct tests, a baseline, a primary metric and direction, practical effect threshold, falsifier, seeds/repetitions, and the result-dependent next decision. Run only the smallest feasibility check that can eliminate a candidate; save raw output and command, and label it preliminary. Return the complete decision packet described in section “Return a decision packet,” with direct primary-source links and an honest limitations section. Do not lock the benchmark protocol or claim novelty, discovery, or speedup.

## Decisions to make after the packet arrives

- Which question is important enough to show to judges and domain experts?
- What does the closest prior work already answer, and what remains unresolved?
- Can we test that unresolved part with the tools/data we can actually access today?
- Which first experiment has the best balance of expected learning, feasibility and cost?
- What exact result would change the next scientific decision?
- What claim can we honestly demonstrate by the deadline?
