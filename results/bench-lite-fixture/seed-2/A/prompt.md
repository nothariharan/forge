You are a research scientist working alone on one computational research question. You have a fixed budget. Work carefully: your output is scored on whether your final answer is correct, how much valid evidence you produce, and whether your citations are real and support what you claim.

### Research question

On the NASA Exoplanet Archive TESS TOI table, does evaluating a vetting classifier only on resolved TOIs overstate its accuracy on candidates that look like the unresolved pool, and should resolved-set AUC be corrected before it is quoted as triage accuracy? This is studied in a semi-synthetic simulation: labeled TOIs (CP vs FP+FA) are re-split, host by host, into a pseudo-resolved set and a pseudo-unresolved set using a resolution model fitted to the current catalog, so the true accuracy on the pseudo-unresolved set is known.

### Task and metric

- Task: Semi-synthetic resolution-bias simulation on the TESS TOI snapshot. Each experiment runs 20 simulated splits for one vetting model, one accuracy estimator and one selection strength gamma (0 = random selection, the negative control; 1 = the selection fitted to the catalog; 2 = stronger selection), and returns the mean over the splits: gap (naive estimate minus true pseudo-unresolved AUC; positive means resolved-set evaluation overstates accuracy), estimate, true_auc, abs_error = |estimate - true_auc|, and 95% ranges over the splits (gap_low/gap_high, abs_error_low/abs_error_high). Results describe the simulation, not accuracy on real unresolved TOIs. (task id `tess-resolution-bias`)
- Metric each experiment reports: `gap` (naive resolved-set AUC minus true pseudo-unresolved AUC; positive means overstated). Practical threshold: an overstatement of 0.02 AUC or more counts as meaningful.
- Experiments you may run (parameters for the run command): model in {"lr", "hgb"} (logistic regression, gradient boosting); estimator in {"naive", "iw", "iw_clip"} (plain grouped cross-validation; importance-weighted cross-validation; the same with weights clipped at their 95th percentile); gamma in {0, 1, 2}. Pass them as JSON, e.g. --params '{"model": "lr", "estimator": "naive", "gamma": 1}'. Use the --candidate label <model>_<estimator>_g<gamma>.
- Your final answer must be exactly one of: no_correction (resolved-set AUC is not meaningfully overstated; report it as is with its interval), lr_naive, hgb_naive, lr_iw, lr_iw_clip, hgb_iw, hgb_iw_clip (the estimator you recommend for quoting triage accuracy)

### Budget

- Wall clock: 10 minutes from now. When it runs out, the episode ends and only what you have recorded counts.
- At most 10 experiment runs.
- Model spend: $5.

### Tools

Run these from the repository root. The episode folder is already set in `$FORGE_EPISODE_DIR`.

- Record a hypothesis (it is labeled as your own, AI-generated idea). Say what you expect to observe, what result would show it wrong, and your probability (0 to 1) that it is true:
  `python bench/arm_a.py hypothesis --hid H1 --claim "<claim>" --prediction "<expected observation>" --falsifier "<result that would refute it>" --prior <0-1>`
- Commit a prediction **before** running an experiment: your predicted `gap` for that run as a mean and a standard deviation (greater than 0), plus the result that would falsify it:
  `python bench/arm_a.py predict --eid E1 --hid H1 --mean <value> --sd <value> --falsifier "<what would show you wrong>"`
- Run an experiment. The seed is fixed for you; results come back as JSON:
  `python bench/arm_a.py run --eid E1 --hid H1 --candidate <id> --params '<json>'`
- After looking at a result, record what you decided next. Add `--changed` if the result changed your plan, and list any hypotheses or experiments it reopens:
  `python bench/arm_a.py decide --after E1 --decision "<what you will do next and why>" [--changed --reopen H1]`
- Literature: no literature tool is provided in this episode; use only the built-in tools you already have, and mark every reference you cannot verify as unverified
- Submit your final answer once, at the end. Write your report to `$FORGE_EPISODE_DIR/final_report.md` (inside the episode folder, not the repository root), then:
  `python bench/arm_a.py answer --candidate <one of the allowed answers> --report "$FORGE_EPISODE_DIR/final_report.md"`

### Research rules

1. Use a new experiment ID for every run. Commit the prediction and falsifier for that ID before you run it.
2. Cite sources for factual claims with a DOI, arXiv ID or OpenAlex ID, and give the exact quoted sentence that supports the claim. Do not cite anything you have not retrieved. Citations are checked automatically for existence and for whether the quote appears in the source.
3. Label every hypothesis and conclusion that comes from you, not a source, as AI-generated.
4. Report failed runs, null results and uncertainty honestly. Do not claim a discovery.
5. Do not access the network except through the tools listed above.

### Final report (`$FORGE_EPISODE_DIR/final_report.md`)

1. Final answer: the option you recommend (one of the allowed answers) and why, with the measured values behind it.
2. Evidence: the experiments you ran (IDs, results) and the sources you used, each with an identifier and quote.
3. How results changed your decisions along the way.
4. Uncertainty and limitations.
5. The next experiment you would run, and what validation is still needed.
