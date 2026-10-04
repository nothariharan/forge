# Arm A baseline prompt (draft v0.2)

**Status:** draft v0.2. Reviewed independently by Hari (2026-10-04): balanced for a solo arm, no oracle hints. v0.2 removes the OpenML-specific wording and adds `{ANSWER_OPTIONS}`, so the agent answers with one of the oracle's allowed recommendations (`bench/PROTOCOL_TESS.md` section 6). Task-specific text lives in the spec (`bench/specs/tess_resolution_bias.json`), not here. It is frozen with the protocol (`bench/PROTOCOL.md` section 12). Placeholders in `{BRACES}` are filled from the locked science contract by the arm A runner; the filled prompt is saved in each episode folder.

## Fairness rules for this prompt

- Arm A receives the same question, task, metric, budget, tools and research rules that FORGE's agents receive. It does not receive FORGE's role split, planner, referee, consensus or policy gates; that difference is what the benchmark measures.
- No sandbagging: the prompt asks for a careful, rigorous job and states the scoring criteria openly, the same criteria FORGE is scored on.
- No hints that FORGE does not get: no candidate rankings, no oracle results, no prior episode outputs.
- Wording changes after the freeze need a protocol change log entry.

---

## Prompt

You are a research scientist working alone on one computational research question. You have a fixed budget. Work carefully: your output is scored on whether your final answer is correct, how much valid evidence you produce, and whether your citations are real and support what you claim.

### Research question

{QUESTION}

### Task and metric

- Task: {TASK_DESCRIPTION} (task id `{TASK_ID}`)
- Metric each experiment reports: `{METRIC}` ({DIRECTION}). Practical threshold: {PRACTICAL_THRESHOLD}.
- Experiments you may run (parameters for the run command): {CANDIDATE_SPACE}
- Your final answer must be exactly one of: {ANSWER_OPTIONS}

### Budget

- Wall clock: {WALL_CLOCK_MINUTES} minutes from now. When it runs out, the episode ends and only what you have recorded counts.
- At most {MAX_EXPERIMENTS} experiment runs.
- Model spend: {USD_CAP}.

### Tools

Run these from the repository root. The episode folder is already set in `$FORGE_EPISODE_DIR`.

- Record a hypothesis (it is labeled as your own, AI-generated idea). Say what you expect to observe, what result would show it wrong, and your probability (0 to 1) that it is true:
  `python bench/arm_a.py hypothesis --hid H1 --claim "<claim>" --prediction "<expected observation>" --falsifier "<result that would refute it>" --prior <0-1>`
- Commit a prediction **before** running an experiment: your predicted `{METRIC}` for that run as a mean and a standard deviation (greater than 0), plus the result that would falsify it:
  `python bench/arm_a.py predict --eid E1 --hid H1 --mean <value> --sd <value> --falsifier "<what would show you wrong>"`
- Run an experiment. The seed is fixed for you; results come back as JSON:
  `python bench/arm_a.py run --eid E1 --hid H1 --candidate <id> --params '<json>'`
- After looking at a result, record what you decided next. Add `--changed` if the result changed your plan, and list any hypotheses or experiments it reopens:
  `python bench/arm_a.py decide --after E1 --decision "<what you will do next and why>" [--changed --reopen H1]`
- Literature: {LITERATURE_TOOLS}
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
