# Science contract (to be locked)

Status: **provisional candidate; corrected one-fold feasibility run recorded; benchmark protocol and full runner validation pending.** Science lead: Hari (proposed).

## Challenge alignment

The governing brief is `docs/references/reference-02.pdf`, Track 03 “Agentic Scientific Discovery.” It requires one specific question, a reproducible computational experiment, and a result that informs the next decision. The planner should compare at least two possible tests and justify its choice by expected learning, feasibility and cost. The Adult task below remains a candidate only; its scientific value and prior art need review before locking it.

## Feasibility candidate (2026-10-04)

- Candidate question: How should missing categorical values be handled on OpenML Adult, and does the best strategy depend on the model?
- OpenML task: [7592 — adult](https://www.openml.org/t/7592); dataset 1590, version 2, public license; target `class`.
- Missingness: dataset contains `?` values in `workclass`, `occupation`, and `native-country` (3,620 rows with at least one missing feature; 6,465 missing cells, after parsing the downloaded ARFF).
- Split: official task protocol is one repetition of stratified 10-fold cross-validation. Feasibility ran repeat 0, fold 0 only: 43,957 training rows / 4,885 test rows.
- Provisional primary metric: ROC AUC, maximize. Secondary: log loss, accuracy, sex subgroup AUC gap, race subgroup AUC gap. The OpenML task API's `evaluation_measures` array is empty, so metric choice needs explicit protocol approval. Accuracy alone is not adequate for this imbalanced task.
- Proposed candidate space from Akshat: mode imputation, mode + indicators for the three affected categorical features, missing as its own category, and dropping those three columns, each with Logistic Regression and HistGradientBoosting; plus HGB's native categorical/missing-value handling (9 candidates total). Provisional practical threshold: 0.003 ROC AUC. Akshat's suggested unit is one candidate evaluated on all ten official folds; seeds control HGB. These values are proposals, not frozen protocol.
- Corrected feasibility comparison: fixed Logistic Regression (`max_iter=1000`, `random_state=0`), same imputation/encoding otherwise; fold repeat 0, fold 0 only. Mode imputation: ROC AUC **0.905763**, log loss **0.321055**, accuracy **0.851382**, fit + predict **5.6798 s**. Mode plus explicit indicators for the three missing categorical columns: ROC AUC **0.906983**, log loss **0.319313**, accuracy **0.853634**, fit + predict **3.8354 s**.
- Correction: the previously reported tie is withdrawn. Its indicator arm used `SimpleImputer(add_indicator=True)` only on numeric features, while Adult's numeric features have no missing values, so it added zero columns. Akshat identified this. The corrected script adds indicators for `workclass`, `occupation`, and `native-country`.
- Runtime excludes download/startup and covers one fit + prediction; timings are local single-fold observations, not a speed claim.
- Setup issue: OpenML Python client installation failed in this environment; task metadata, data, and official split were fetched directly from OpenML APIs. Local pandas was installed to run the prototype. Reproduce the corrected one-fold check with `python tools/feasibility_openml7592.py --output schemas/examples/openml-7592-feasibility.json`. Adult ARFF SHA-256: `77aa1703717a29f0b5642e94c3ba1defd2486f0b34d4d8eccc1b37a5f7d226b0` (same raw output as the JSON artifact).
- Initial candidate rejected: OpenML task 31 (`credit-g`) was inspected and found to have **zero** missing feature values, so it cannot answer the candidate question. The paper/catalogue hint that led to checking it was not sufficient evidence.
- Interpretation: feasibility only. One fold and one seed. The early estimate favors indicators slightly, but cannot establish a general effect. It does not establish generalization or benchmark performance. Adult is an income prediction dataset; fairness subgroup metrics and their interpretation need review.
- Runner status: `tools/openml_run.py` now exposes Akshat's requested `run(task_id, params, seed)` interface and computes proposed metrics over all ten official folds. Syntax compilation succeeded, but a full ten-fold invocation has not yet completed in this environment; do not use it for an oracle sweep until that call is validated.
- Next action: Akshat to freeze/revise the candidate space, metric definitions (including subgroup AUC gap), practical threshold, and budgets in `bench/PROTOCOL.md`; an outside-lane teammate reviews the baseline prompt. Then validate the full runner and oracle spec before comparative episodes.

### Machine-readable run output

```json
{
  "status": "FEASIBILITY_ONLY_NOT_BENCHMARK_EVIDENCE",
  "task_id": 7592,
  "dataset_id": 1590,
  "dataset_version": 2,
  "fold": "repeat 0, fold 0",
  "metric": "ROC AUC (provisional; maximize; task metadata has no evaluation measure)",
  "results": [
    {"comparison": "median_mode", "roc_auc": 0.9057629781188046, "log_loss": 0.3210545615658956, "accuracy": 0.851381780962129, "runtime_seconds": 5.6798},
    {"comparison": "median_mode_plus_categorical_missing_indicators", "roc_auc": 0.9069832808625405, "log_loss": 0.3193132400910688, "accuracy": 0.8536335721596725, "runtime_seconds": 3.8354}
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
