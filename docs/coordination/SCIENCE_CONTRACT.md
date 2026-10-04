# Science contract (to be locked)

Status: **No scientific question or benchmark protocol is locked. The Kepler exoplanet planet-outcome target is CLOSED by measurement; the TESS resolved-disposition target is the single surviving exoplanet candidate and still has an open independent-reference-standard gate.** Science lead: Hari.

**2026-10-04 update — the exoplanet target has been resolved, negatively for Kepler.** A reproducible label-availability audit ([`tools/audit_exo_target_feasibility.py`](../../tools/audit_exo_target_feasibility.py), artifact [`schemas/examples/exo-target-feasibility.json`](../../schemas/examples/exo-target-feasibility.json)) established that:

- **Censoring rule, now fixed:** `CANDIDATE` and `NOT DISPOSITIONED` are unresolved. They are censored — excluded from the labeled cohort, reported separately, and never recoded as positives.
- **Outcome rule:** an outcome is observable only at a release later than the one supplying features. Objects already labeled at the feature release are excluded from the cohort, so training and evaluation objects are disjoint by construction.
- **Kepler is closed.** The CONFIRMED count is effectively frozen after Q1-Q16: 2735 → 2748 by the cumulative table, **+13 objects (+0.48%)**, while the catalog grew +30.2%. Every unresolved→resolved cohort was enumerated and every one fails a stated 200-per-class minimum: the largest confirmed class anywhere in the Kepler disposition history is **28** objects, and DR25 candidates produce **0** confirmations through 2026.
- **Kepler false positives are rejected on circularity**, not class size. The disposition was produced by the same photometric/astrometric quantities the features encode, so such a model distills the archive’s own vetting rules.
- **Join hazard found:** `kepoi_name` is not stable across deliveries. A strict Q1-Q16 → DR24 join drops 1356 of 7348 rows including 27 later-confirmed objects. Any exoplanet protocol must use a two-tier join and report ambiguity.
- **TESS survives on class size.** 1420 `KP`/`CP` vs 1314 `FP` = **2734** usable labeled objects (51.9% positive), 5400 censored, host grouping on `tid` with 109 multi-TOI hosts. `ctoi_alias` is **not** an independent reference standard — it is populated for all resolved rows including all false positives — so the target remains open until an independent adjudication source is demonstrated.

See [`SCIENCE_DECISION_PACKET.md`](SCIENCE_DECISION_PACKET.md) for the full tables and the open gate list. Adult remains retired as a science candidate and retained only as the deterministic runner/ledger integration task. Nothing is locked pending that gate and a prior-art review with the benchmark lead.

**2026-10-04 gate update — the TESS data gates are now measured, and one science-adjacent smoke test has been preregistered and run.**

- **Independent reference for positives: PASSES at host-star level.** `tid` → `pscomppars.tic_id` matches **88.7%** of `CP` hosts against **0.23%** for `FP`, a separation of 0.885. Internal check: 717 of 721 matched `CP` hosts have a TESS-era discovery year, while 420 of 587 `KP` hosts do not, confirming `KP` is a previous-survey catalog lookup. Artifact: [`schemas/examples/tess-reference-standard.json`](../../schemas/examples/tess-reference-standard.json).
- **Label semantics settled by measurement:** positive = `CP`; exclude `KP`; **`FA` is a negative**, because its 0.030 host-match rate behaves like `FP` (0.0023) rather than `CP`. Censored = `PC`/`APC`.
- **Host disjointness: `tid` is the TIC ID,** so grouping on `tid` is star-level grouping. 223 hosts in the T1 cohort carry more than one TOI.
- **Prospective temporal split: impossible.** The TOI table has no disposition-assignment date, only `toi_created`, `rowupdate` and `release_date`. Remove it from the protocol.
- **Still no independent source for negatives.** `FP` remains a TFOPWG committee judgment; that asymmetry is a permanent limit, not a task to close.
- **Prior art fails for plain TESS classification** (Kopparapu et al. 2026 is nearly the same design). The direction survives only as the resolution-bias audit, which still needs its own Referee search. That search is now the main scientific risk.
- **T1 resolution-shift smoke test: prediction supported.** Out-of-fold AUC for resolved vs unresolved TOIs is **0.7616**, 95% cluster-bootstrap CI **[0.7492, 0.7737]**, permutation null mean 0.4973. Resolved and unresolved candidates are not exchangeable given triage features. Timestamps add only 0.038 AUC, so the shift is not merely an age artifact. **This is a data property, not an accuracy result: 0.7616 must never be quoted as an accuracy overstatement.** Preregistration: [`TESS_RESOLUTION_SHIFT_PREREGISTRATION.md`](TESS_RESOLUTION_SHIFT_PREREGISTRATION.md).

**Remaining before lock:** the resolution-bias question wording, T2's accuracy-gap estimate and practical threshold, and the prior-art search on the resolution-bias question itself.

**2026-10-04 earlier update — Adult is retired as a science candidate, not as a runner check.** OpenML Adult 7592 keeps its role as the deterministic runner/ledger integration task. An audit found the first precision-transfer analysis mislabeled candidate status as planet truth and reused training objects in its temporal score; those metrics are withdrawn.

## Challenge alignment

The governing brief is `docs/references/reference-02.pdf`, Track 03 “Agentic Scientific Discovery.” It requires one specific question, a reproducible computational experiment, and a result that informs the next decision. The planner should compare at least two possible tests and justify its choice by expected learning, feasibility and cost. The Kepler target failed the target-validity gate on measurement; the TESS candidate has passed target validity but has not passed the independent-reference-standard or prior-art gates.

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
- Next action: the target/cohort step is **done** for TESS and **closed** for Kepler. Remaining, in order: (1) demonstrate an independent adjudication source for `KP`/`CP` and report the cross-match rate, since `ctoi_alias` does not qualify; (2) verify `tid` → TIC host disjointness; (3) complete the prior-art review covering the 2026 instrument-agnostic prioritization paper. Only then does Akshat review and co-freeze the benchmark protocol. If the reference-standard gate fails, reopen the domain shortlist outside astronomy rather than falling back to Kepler false positives. Do not use the withdrawn exoplanet scores or the Adult one-seed sweep as benchmark evidence.

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
