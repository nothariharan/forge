Run id: lite-B-3

Investigate the research question below with the FORGE team and record every handoff in the ledger.

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

### Research rules

1. Use a new experiment ID for every run. Commit the prediction and falsifier for that ID before you run it.
2. Cite sources for factual claims with a DOI, arXiv ID or OpenAlex ID, and give the exact quoted sentence that supports the claim. Do not cite anything you have not retrieved. Citations are checked automatically for existence and for whether the quote appears in the source.
3. Label every hypothesis and conclusion that comes from you, not a source, as AI-generated.
4. Report failed runs, null results and uncertainty honestly. Do not claim a discovery.
5. Do not access the network except through the tools listed above.

### How to run this episode

Run the full loop (planner, safety, experimenter, analyst, repeated) until the question is answered or the budget runs out, then record RUN_COMPLETED. Nobody will reply during the episode.
No literature tool is provided in this episode, so skip the librarian and the referee: record no EVIDENCE_ADDED or NOVELTY_VERDICT, give the hypothesizer the research question and task text above as its input, and tell the planner the novelty check was not run.

### Running an experiment

Each experiment is one run of this command (the experimenter runs it behind the P6 gate); the seed is fixed:

    .venv/bin/python tools/tess_bias_run.py --model <lr|hgb> --estimator <naive|iw|iw_clip> --gamma <0|1|2> --seed 3

It prints JSON; its `metrics` object holds the metric. Label each experiment with the candidate id `<model>_<estimator>_g<gamma>` and put it in the RUN_STARTED and RUN_FINISHED payloads as "candidate".

### Final answer

End the run by recording RUN_COMPLETED with {"status": "completed", "summary": "<one paragraph>", "candidate": "<id of the candidate you recommend>"}. Only the candidate recorded there is scored.
