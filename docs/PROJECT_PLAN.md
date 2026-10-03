# FORGE implementation plan

**Status:** bootstrap plan; no scientific question, Omnigent smoke test, or benchmark result is locked yet.

## Objective and evaluation thesis

Build a computational research lab where specialist agents use tools and structured handoffs to generate cited evidence, propose labeled hypotheses, preregister falsifiable predictions, select bounded experiments, analyze results, and change the next action. The project must show (1) actual Omnigent orchestration, (2) a genuine feedback/replanning loop, and (3) a fair measured comparison against a single-agent baseline. We will report measured outcomes, even if the multi-agent system is slower or less accurate.

## Non-negotiable evidence standards

- The exact research question, data split/task, outcome metric, baselines, budget, seeds/repetitions, and stopping rule are committed before benchmark runs.
- Baseline and FORGE arms receive the same question, data, compute/time/token budget, allowed tools, and scoring rubric wherever possible. Document unavoidable differences.
- Separate setup/development time from timed task execution. Define the denominator for every speed or throughput number.
- Report wall time, human time if measured, model/tool cost, completed valid experiments, citation resolution/support rate, and task quality with uncertainty and raw run records.
- Do not conflate iteration throughput with discovery quality or claim a scientific discovery from benchmark evidence alone.
- A novelty search can only say what was found in the searched sources and when; it cannot establish universal novelty.

## Decisions to lock in the first working session

1. Exact ML question framed as a falsifiable comparison, selected by the science lead after a small feasibility run.
2. One OpenML task/dataset with stable task ID, version/snapshot, license, split protocol, and a metric where direction and practical effect threshold are clear.
3. Experiment budget and safe execution limits; baseline agent/model and allowed tools.
4. Outcome/quality rubric, number of seeds and repetitions, primary metric, secondary metrics, and analysis method.
5. Omnigent version/commit, Claude Code invocation mode, actual agent/policy config format, handoff representation, and a minimal successful two-agent run plus one policy denial.

Do not build planner assumptions around an unverified Omnigent feature. If the smoke test fails, record the failure and choose a transparent fallback runner while retaining Omnigent evaluation as an unresolved rubric risk.

## Workstreams and interfaces

### Orchestration lead — `work/orchestration`

Owns `omnigent/`, `agents/`, `policies/`. Inspect upstream docs and pin a tested Omnigent revision. Configure the smallest useful specialist graph: Librarian → Hypothesizer → Referee → Planner → Experimenter → Analyst, with Safety gates. Prove structured handoff and one enforced denial. Define how each accepted/denied handoff becomes a ledger event. Produce runnable local instructions, not illustrative-only YAML.

### Science + planner — `work/science`

Owns question/task selection, `tools/openml_run.py`, experiment runner, `core/beliefs.py`, preregistration, prediction scoring, surprise, and planner. Publish the experiment input/output contract early. A minimal experiment must run without the agent system, with fixed seed and machine-readable metrics. The planner can start with a transparent expected-information-gain (EIG) estimate only if outcome likelihoods are specified and calibrated; otherwise implement a simpler documented heuristic and avoid implying optimality. Define exactly how surprise is computed from the preregistered predictive distribution and observed outcome, including zero-probability safeguards.

### Benchmark + rigor — `work/benchmark`

Owns `bench/`, baseline single-agent arm, metric definitions, seeds/error bars, citation checker, top-finding prior-art check, README claims/limits, submission and next-experiment write-up. First deliver a protocol and baseline runner using the locked question, independent of orchestration completion. Compare equal budgets; retain all attempts and failures. Use paired seeds where valid. Report denominators, costs, uncertainty, and tool/model versions. Do not use LLM self-grading as sole ground truth; use deterministic task metrics and blinded/manual rubric review where needed.

### Core + UI + CLI — `work/core-ui`

Owns `schemas/`, `core/ledger.py`, `server.py`, `cli/`, and `ui/`. Implement event validation, append-only hash-chained storage, replay, and read-only UI/CLI consumers against a fake event generator at once the event schema is agreed. SSE reconnection and replay should use sequence IDs; test corrupted/tampered chains. UI shows current run, agents, evidence, budget, experiment state, gates, and chronological events; include a replay mode so the demo works offline.

### Coordination protocol

Science lead announces a versioned experiment contract before other lanes depend on it. Core/UI announces a versioned `schemas/event.schema.json` and sample JSONL fixture. Orchestration maps its actual state changes to those events. Benchmark records the exact code/config/model/data revision for both arms. Breaking changes require a short decision note and coordinated updates across owners.

## Architecture and data flow

1. CLI creates a run with question, budget, dataset/task, config revision, and run ID.
2. Omnigent starts the configured Claude Code harness specialists and enforces policy/tool permissions.
3. Librarian retrieves sources through approved literature tools; claims reference resolvable records and quote spans where available. Citation checks distinguish identifier resolution from claim support.
4. Hypothesizer returns schema-valid hypotheses labeled AI-generated. Referee searches for prior art and returns NOVEL / KNOWN / CONTRADICTED / UNCERTAIN with sources and search scope.
5. Planner selects an experiment under the remaining budget. Prediction distribution, falsifier, metric, seed, code/data version, and selected plan are committed before execution.
6. Safety policy evaluates resource/risk/approval requirements. Denials and human resolutions are ledgered.
7. Experimenter runs a deterministic computational experiment in a constrained worker and emits code hash, environment, data/task ID, seed, metrics, runtime, and cost.
8. Analyst calculates effect/uncertainty and compares observation with preregistration. Surprise or meaningful evidence updates beliefs and must change the next decision (or record why it did not).
9. Append-only ledger is the audit/replay source. UI and CLI subscribe/read; they do not become alternate state stores.
10. Bench runner executes matched single-agent and FORGE arms and emits a report plus raw artifacts.

## Proposed contracts (subject to implementation)

- `EvidencePacket`: claims, references (DOI/arXiv/OpenAlex IDs and URLs), source spans, retrieval timestamp, and verification statuses.
- `Hypothesis`: stable ID, claim, prediction distribution, falsifier, prior/belief, AI-generated marker, and evidence references.
- `NoveltyVerdict`: label, supporting/contradicting prior art, query/source coverage, timestamp, confidence/uncertainty.
- `ExperimentSpec`: ID, parent hypothesis, design, metric, expected outcomes, estimated cost, budget, seed, and preregistration hash.
- `RunRecord`: experiment ID, code/data/environment hashes or versions, seed, metrics, uncertainty inputs, start/end, resource use, exit status.
- `Finding`: effect estimate, interval, analysis method, limitations, analyst trajectory IDs, agreement/disagreement.
- `Gate`: action, policy, risk/reason, pending/approved/denied state, human actor and timestamp when resolved.
- `LedgerEvent`: monotonic sequence, UTC timestamp, run/agent/type, validated payload, AI marker, previous hash and current hash.

Keep interfaces small; implement JSON Schema or equivalent validators as code. Never treat model prose as a valid structured result without validation.

## Algorithms: use only where testable

### Preregistered predictive distributions and surprise

Commit a predictive distribution before the run. For categorical outcomes compute `surprise = -log(max(p_prior(observed), epsilon))`; for continuous outcomes use a predeclared predictive density/log score and report its calibration limitations. Surprise is not automatically evidence of importance: the analyst must distinguish surprising noise from an interpretable effect. A threshold is chosen before evaluation. A trigger asks Planner to reconsider and logs the old and new decisions.

### Budget-aware experiment selection

Candidate score may be estimated information gain per expected cost, `EIG(e) / cost(e)`, where EIG is the expected KL divergence between posterior and prior over explicitly modeled outcomes. Enumerate/Monte Carlo candidate outcomes and disclose approximations. Validate scores against the actual decision utility on the chosen task. If likelihood models are unsupported, use a transparent heuristic baseline and include an ablation; do not market an uncalibrated score as Bayesian optimal design.

### Novelty referee

Use retrieval plus structured counterargument and independent query formulation. The output is a triage label with cited prior art and query coverage, not a novelty guarantee. KNOWN findings are preserved as useful negative outcomes and generally do not consume experiment budget unless marked replication.

### Consensus analysis

Only use multiple analyst trajectories if compute/time permits and a stable analysis rubric exists. Report raw answers, agreement statistic, and deterministic result. Agreement does not replace statistical validity or expert review. An ablation determines whether extra trajectories improve accuracy enough to justify cost.

### Hash-chained ledger

Serialize events canonically and hash previous hash plus canonical event fields. Include schema/version identifiers. `forge verify` checks sequence, event schema, and hash chain. Hash chaining detects modifications relative to a trusted head; it does not alone prove who created an event or prevent full-history replacement.

## Delivery phases and exit gates

### Phase 0 — repository and feasibility

- Archive source documents with provenance; create role branches and contributor rules.
- Inspect Omnigent and Claude Code prerequisites, pin versions, run two-agent handoff, structured schema validation, and one enforced policy denial.
- Run one OpenML task manually with deterministic seed and save raw output.
- **Exit:** dependencies and constraints known; exact task/metric feasibility is demonstrated; risks recorded.

### Phase 1 — scientific protocol and baseline

- Lock question, dataset/task, split, metric, primary comparison, budget, seeds, repetitions, scoring rubric, and stopping rule.
- Implement baseline arm and raw artifact format before tuning FORGE.
- **Exit:** a baseline run can be reproduced from a clean checkout; protocol is committed before comparative runs.

### Phase 2 — contracts and audit trail

- Finalize handoff/event schemas and fixtures. Implement validation, ledger, hash verification, fake event stream, CLI tail/status, and replay view.
- **Exit:** malformed events are rejected, valid fixture replays, tampering is detected.

### Phase 3 — minimum closed loop

- Connect Omnigent specialists with tool calls, policy enforcement, evidence/hypothesis/experiment contracts, bounded runner, analysis, and replanning.
- **Exit:** one real result demonstrably changes (or explicitly leaves unchanged with recorded rationale for) a subsequent experiment choice; the full path is traceable in ledger.

### Phase 4 — comparison and rigor

- Run preregistered matched arms/repetitions and ablations only if resources allow. Check references and prior art for the top finding. Compute uncertainty and costs from raw artifacts.
- **Exit:** report is generated from artifacts and includes failures, limitations, and next experiment.

### Phase 5 — presentation and handoff

- Build UI around real and replayed events, record two-minute demo, finalize README, submission narrative, setup and reproduction commands, and next-experiment document.
- **Exit:** demo can be replayed offline; no result claims lack raw evidence; clean-checkout reproduction path is documented.

## Time-boxed 24-hour execution suggestion

- Before clock: Phase 0 smoke tests and dependency installation.
- Hours 0–2: science locks task/metric/protocol; benchmark specifies paired baseline; core publishes event fixture; orchestration validates minimum graph.
- Hours 2–6: parallel baseline runner, Omnigent handoff/policy, ledger and UI fake-event consumer.
- Hours 6–12: close one real computational loop and save artifacts.
- Hours 12–18: matched runs, citation/novelty checks, budget/quality analysis; stop feature work if reliability is threatened.
- Hours 18–21: replay UI, offline demo, fix only blocking issues.
- Hours 21–24: reproduce cleanly, write limitations/next experiment, capture demo and submission evidence.

Cut order: polish/extra rooms → multi-analyst ensemble → tournament ranking → advanced EIG. Preserve the actual Omnigent proof, baseline, a real result-driven replan, human gate, ledger/replay, and honest measurement.

## Submission outputs

- Source and pinned setup, tested Omnigent configuration/policies, agent prompts and contracts.
- Reproducible computational experiment, dataset/task identifiers, seeds and raw results.
- Baseline comparison and metric definitions with denominators, costs, uncertainty, and all exclusions.
- Citation-resolution/support report and scoped novelty search for the top finding.
- Demo and replay, architecture overview, known failure modes, and concrete next experiment.

## Open issues

- Verify the hackathon brief, event schedule, and rubric from the archived official brief PDF.
- Confirm exact Omnigent release/config/policy APIs against upstream source and smoke test.
- Confirm Claude Code account/runtime availability and team access; do not commit secrets.
- Science lead to lock exact OpenML task and benchmark question.
- Map original PDF filenames to meaningful titles by inspecting their title pages; until then their archive names are neutral IDs.
- Verify every named paper/tool/algorithm source from primary references before submission citation.
