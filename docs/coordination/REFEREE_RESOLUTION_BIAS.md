# Referee search: TESS resolution-bias question

- **Owner:** Akshat (benchmark + rigor)
- **Date:** 2026-10-04
- **Question searched:** does a vetting model's accuracy measured on resolved TOIs overstate its accuracy on the unresolved candidates it is used to triage, and can a correction (importance weighting / positive-unlabeled methods) recover it? (`bench/PROTOCOL_TESS.md` section 1)
- **Status:** search complete for this pass. **Verdict: partial overlap.** The method is known. The phenomenon is documented qualitatively. The specific quantification was **not found in this search**. That is not proof of novelty.

## Method and coverage

- **Service:** general web search (US index). arXiv, ADS, OpenAlex and the publishers' pages could not be opened directly from this environment (egress blocked), so this is a **listing-level** search: titles, abstracts and snippets as indexed, not full texts.
- **Not covered:** full-text reading, citation chaining ("cited by"), ADS keyword search, and non-English literature. A domain expert or a full-text pass could find closer work.
- **Citations below** were checked to exist via their search listings. They still have to pass `tools/citation_check.py` (resolution and quote check) before they appear in the submission.

### Query log (2026-10-04)

| # | Query | Closest relevant hits |
|---|---|---|
| 1 | machine learning classification TESS objects of interest false positive confirmed planet TFOPWG disposition labels | Osborn 2020; Yu 2019; Tey 2023; ExoMiner++; NotPlaNET |
| 2 | Kopparapu 2026 … candidate prioritization Kepler TESS Roman | Kopparapu et al. 2026 |
| 3 | exoplanet candidate classifier selection bias training labels confirmed planets not representative unresolved candidates covariate shift censoring evaluation TESS | ExoNet 2026; Kopparapu 2026; arXiv 2512.00967 |
| 4 | positive-unlabeled learning exoplanet candidates vetting … TESS Kepler | no exoplanet PU-learning paper found; general PU learning only |
| 5 | selection bias exoplanet candidate vetting classifier evaluated on confirmed planets overestimates performance unconfirmed candidates | Robnik et al. 2026; Armstrong et al. 2021 |
| 6 | positive unlabeled learning planet candidates transit survey vetting class prior estimation | general PU / class-prior literature only (Bekker & Davis survey; Jain et al. 2017) |
| 7 | covariate shift importance weighting evaluation exoplanet machine learning training set not representative of candidates Kepler TESS | Sugiyama, Krauledat & Müller 2007 (IWCV); no exoplanet application found |
| 8 | "training set" bias confirmed planets false positives vetting model performance on planet candidates differs long period low signal-to-noise | DART-Vetter 2025; Shallue & Vanderburg 2018 |
| 9 | TESS objects of interest machine learning evaluated only on dispositioned TOIs performance on planet candidates PC unknown labels caveat | ExoMiner++ (applies to PC TOIs); arXiv 2512.00967 |
| 10 | arXiv 2601.07465 … (details of the closest Kepler result) | Robnik, Seljak, Jenkins & Bryson 2026 |

## Closest prior work

| Work | What it establishes | Overlap with our question |
|---|---|---|
| Sugiyama, Krauledat & Müller 2007, JMLR 8, "Covariate Shift Adaptation by Importance Weighted Cross Validation" | Under covariate shift, ordinary CV is biased. Importance-weighted CV (IWCV) is unbiased. | **Our `iw` / `iw_clip` estimators are IWCV.** The correction method is not new and must be cited as such. |
| Kopparapu et al. 2026, AJ 172, 100 (arXiv:2606.07769) | ML prioritization on confirmed vs FP from TESS and Kepler, using catalog features. Notes that resolved candidates had characteristics "amenable to classification". | States the bias **qualitatively**. No quantification of the overstatement and no correction evaluated, as far as the listing shows. |
| Robnik, Seljak, Jenkins & Bryson 2026, MNRAS 547 (arXiv:2601.07465) | A new Kepler pipeline recovers confirmed planets but flags a considerable share of unconfirmed candidates as likely false alarms, especially at long period and low S/N. | **Strong qualitative support** that unresolved candidates are harder and differ from resolved ones (Kepler, not TESS). It does not measure a classifier's accuracy overstatement. |
| Shallue & Vanderburg 2018, AJ 155, 94; DART-Vetter 2025 (arXiv:2506.05556) | Vetting performance drops for low-MES / long-period signals, and training sets contain few low-MES positives. Human labels carry vetter bias. | Documents **where** models are weak and that training labels are biased. Does not frame it as resolved-set evaluation overstating triage accuracy. |
| ExoMiner++ (arXiv:2502.09790); arXiv 2512.00967; ExoNet 2026 (arXiv:2604.15560) | Classifiers applied to TESS `PC` TOIs; calibrated vetting. | Deploy on the unresolved pool, but evaluate on dispositioned objects, which is the practice our question audits. |
| Positive-unlabeled learning (Bekker & Davis 2020 survey; Jain et al. 2017, "Recovering true classifier performance in PU learning"; Bekker et al. 2019, PU under selected-at-random) | Methods to estimate class priors and true performance from positive + unlabeled data. The SAR setting matches "resolution depends on features". | General methods; **no exoplanet-vetting application found**. A possible extension, not used in our estimators. |

## Verdict and consequences for the protocol

1. **Method: KNOWN.** The `iw` estimators are IWCV (Sugiyama et al. 2007). Any write-up must present them as an existing correction applied to this setting, never as a new method.
2. **Phenomenon: documented qualitatively.** Resolved and unresolved candidates differ, and models are weaker in the harder regimes (Robnik et al. 2026; Shallue & Vanderburg 2018; DART-Vetter 2025; Kopparapu et al. 2026). Our T1 result (current-catalog separability, AUC 0.76) is consistent with that, not a discovery.
3. **Specific quantification: not found in this search.** We did not find a measured estimate of how much resolved-set evaluation overstates TESS vetting AUC on a deployment-like population, nor an evaluation of IWCV-type correction for it. This is the only residual gap, and it is **conditional** on a listing-level search.
4. **Claim wording (applied to `bench/PROTOCOL_TESS.md` section 9):** "We quantify, in a semi-synthetic simulation, a selection effect that prior work describes qualitatively, and test an existing correction (IWCV)." No "first", "novel" or "discovery" language.
5. **Next search, if time allows:** full-text and citation-chaining pass over Kopparapu et al. 2026 and Robnik et al. 2026, plus an ADS query for "selection bias" AND "vetting" AND ("TESS" OR "Kepler").
