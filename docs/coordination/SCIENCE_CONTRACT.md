# Science contract (to be locked)

Status: **No scientific question or benchmark protocol is locked. Astronomy/exoplanet catalog vetting is the provisional product context only. The original exoplanet classifier precision figures are invalidated; the replacement feasibility artifact is a disposition-count audit with no model evaluation.** Science lead: Hari.

**2026-10-04 update — Adult is retired as a science candidate, not as a runner check.** OpenML Adult 7592 keeps its role as the deterministic runner/ledger integration task. The astronomy/exoplanet direction is provisional. An audit found the first precision-transfer analysis mislabeled candidate status as planet truth and reused training objects in its temporal score; those metrics are withdrawn. The corrected artifact reports catalog transitions only. See [`SCIENCE_DECISION_PACKET.md`](SCIENCE_DECISION_PACKET.md). Nothing is locked pending a valid target/split and prior-art review with the benchmark lead.

## Challenge alignment

The governing brief is `docs/references/reference-02.pdf`, Track 03 “Agentic Scientific Discovery.” It requires one specific question, a reproducible computational experiment, and a result that informs the next decision. The planner should compare at least two possible tests and justify its choice by expected learning, feasibility and cost. The exoplanet direction has not passed its target-validity or prior-art gates.

## Prior-art/value screen (2026-10-04)

The current question—whether categorical missing-value handling changes predictive performance on Adult—is not a new research direction. A 2016 supervised-imputation study explicitly evaluates Adult with missing categorical data and perturbations ([arXiv:1610.09075](https://arxiv.org/abs/1610.09075)); a 2020 benchmark compares imputation strategies across predictive models and datasets ([arXiv:2007.02837](https://arxiv.org/abs/2007.02837)). Related work already studies data-preparation effects on Adult fairness ([arXiv:1910.02321](https://arxiv.org/abs/1910.02321)) and how imputation choices affect group fairness ([Jeanselme et al., ML4H 2022](https://proceedings.mlr.press/v193/jeanselme22a.html)).

**Inference and recommendation:** the current mode-vs-indicator comparison is useful feasibility work, but is too close to established studies to lock unchanged as the submission's scientific question or present as a breakthrough. Keep Adult as a fast engineering/runner validation task. Before locking science, specify a distinct gap that matters to a domain expert, search directly for that gap, and be ready to choose another question/domain. A fairness extension alone is not automatically novel given the prior work above.

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
- Runner validation (2026-10-04): isolated Python 3.12.10 with NumPy 2.2.6, pandas 2.2.3, scikit-learn 1.6.1, SciPy 1.15.3, and threadpoolctl 3.6.0 successfully ran one complete ten-fold candidate (logistic/mode, seed 1). The default environment's pandas import still crashes with Windows exit status `-1073740022`; do not use it. SciPy is pinned because the latest SciPy selected by pip emitted sklearn solver-option warnings. The runner now copies its cached feature frame before native HGB categorical conversion so sequential oracle candidates cannot mutate shared cached data.
- Exploratory sweep (2026-10-04): all nine proposed Adult candidates ran over the official 10 folds once at seed 1; total elapsed time 165.271 s, excluding interpreter startup and cached dataset download. Raw machine-readable metrics and environment details: [`schemas/examples/openml-7592-sweep-seed1.json`](../../schemas/examples/openml-7592-sweep-seed1.json). One seed is not inferential evidence and this is not the A-vs-B agent benchmark. The sweep is useful only for exercising the runner and inspecting candidate feasibility. HGB's higher AUC does not establish a useful scientific finding or novelty.
- Setup/reproduction: create a Python 3.12 venv, install `requirements-science.txt`, then call `tools.openml_run.run(7592, {"model": "logistic", "strategy": "mode"}, seed=1)`; for exploratory metrics see the recorded JSON artifact. No OpenML Python client is needed; task metadata/data/splits are downloaded directly by the runner. Dataset cache is user-local and is not committed.
- Next action: satisfy the lock gate in [`SCIENCE_DECISION_PACKET.md`](SCIENCE_DECISION_PACKET.md): choose an observed outcome, obtain independent held-out objects, define unknown/censored labels, and review the closest astronomy work. Akshat reviews target, split, metric and then freezes the benchmark protocol only after the science lead approves that contract. Do not use the withdrawn exoplanet scores or the Adult one-seed sweep as benchmark evidence.

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
