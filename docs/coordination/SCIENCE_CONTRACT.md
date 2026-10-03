# Science contract (to be locked)

Status: **candidate selected; feasibility run complete; benchmark protocol pending Akshat's review.** Science lead: Hari (proposed).

## Feasibility candidate (2026-10-04)

- Candidate question: On OpenML Adult, does adding missingness indicators to median/mode imputation change logistic-regression classification accuracy?
- OpenML task: [7592 — adult](https://www.openml.org/t/7592); dataset 1590, version 2, public license; target `class`.
- Missingness: dataset contains `?` values in `workclass`, `occupation`, and `native-country` (3,620 rows with at least one missing feature; 6,465 missing cells, after parsing the downloaded ARFF).
- Split: official task protocol is one repetition of stratified 10-fold cross-validation. Feasibility ran repeat 0, fold 0 only: 43,957 training rows / 4,885 test rows.
- Metric: accuracy, maximize. The OpenML task API's `evaluation_measures` array is empty, so accuracy is explicitly selected for this feasibility check and is not represented as the task's prescribed measure.
- Fixed model: `LogisticRegression(max_iter=1000, random_state=0)` with numeric median imputation + standardization and categorical most-frequent imputation + one-hot encoding.
- Comparison A: median/mode imputation, no missingness indicators — accuracy **0.85138**, fit + predict **4.7141 s**.
- Comparison B: same pipeline plus missingness indicators for numeric features — accuracy **0.85138**, fit + predict **9.4671 s**.
- Runtime excludes download/startup and covers one fit + prediction; timings are local single-run observations, not a speed claim.
- Setup issue: OpenML Python client installation failed in this environment; task metadata, data, and official split were fetched directly from OpenML APIs. Local pandas was installed to run the prototype. The run script is `tools/feasibility_openml31.py` (filename retained though the candidate was changed to task 7592). Adult ARFF SHA-256: `77aa1703717a29f0b5642e94c3ba1defd2486f0b34d4d8eccc1b37a5f7d226b0`.
- Initial candidate rejected: OpenML task 31 (`credit-g`) was inspected and found to have **zero** missing feature values, so it cannot answer the candidate question. The paper/catalogue hint that led to checking it was not sufficient evidence.
- Interpretation: feasibility only. One fold and one seed, and both strategies tied to the displayed precision. This does not establish equivalence, generalization, or a benchmark result. Accuracy may hide credit/labor-market subgroup harms and is not the final metric recommendation.
- Next action: Akshat should review task/metric/comparison, recommend a decision-relevant metric and repetition plan, and identify any benchmark leakage or fairness concerns before any preregistered comparative runs.

### Machine-readable run output

```json
{
  "status": "FEASIBILITY_ONLY_NOT_BENCHMARK_EVIDENCE",
  "task_id": 7592,
  "dataset_id": 1590,
  "dataset_version": 2,
  "fold": "repeat 0, fold 0",
  "metric": "accuracy (maximize; chosen for feasibility because task metadata has no evaluation measure)",
  "results": [
    {"comparison": "median_mode", "accuracy": 0.851381780962129, "runtime_seconds": 4.7141},
    {"comparison": "median_mode_plus_missing_indicators", "accuracy": 0.851381780962129, "runtime_seconds": 9.4671}
  ]
}
```

Before implementation relies on the science choice, fill in and commit:

- Research question and why it matters:
- Hypothesis / alternatives (explicitly AI-generated where applicable):
- OpenML task ID, dataset/version, license, split protocol:
- Experiment/intervention and allowed toolchain:
- Primary metric, direction, practical effect threshold:
- Secondary metrics:
- Prediction distribution and falsifier:
- Baseline arm and identical budget definition:
- Number of repetitions/seeds and uncertainty method:
- Runtime, cost, and resource limits:
- Exclusions and stopping rule:
- Known prior work and search scope:
- Raw artifact location and reproduction command:

Science lead publishes a machine-readable experiment input/output example under `schemas/examples/` for core/UI, Omnigent, and benchmark owners before they finalize downstream contracts.
