# FORGE contributor and agent guide

## Mission
FORGE is a computational scientific discovery lab for Hack-Nation × Databricks, Track 03. It is intended to orchestrate specialist Claude Code harness agents through Omnigent so they can move through a measured, reproducible loop: question → cited evidence → explicitly AI-generated hypothesis → preregistered prediction and falsifier → computational experiment → analysis → changed next decision. It is a research assistant, not an autonomous authority or proof of scientific discovery.

## Source of truth and current status
- `docs/` contains the supplied design/planning material and source PDFs. Treat them as references; claims and algorithms must be independently verified and cited before appearing as established facts in a submission.
- `docs/PROJECT_PLAN.md` is the current implementation plan and decision log. Update it when a decision changes.
- The official target is Track 03, **Agentic Scientific Discovery**, in [`docs/references/reference-02.pdf`](docs/references/reference-02.pdf). The separate `docs/references/hackathon-brief.pdf` is an ElevenLabs AI Apprentice brief and is not the FORGE rubric. OpenML Adult task 7592 is currently a feasibility candidate, not a locked scientific question or benchmark protocol.
- Omnigent is the underlying agent runtime, harness-composition and policy-enforcement layer. FORGE is the scientific workflow and user-facing lab. The current graph has partial smoke-test evidence: multi-harness handoff and P2 denial passed; P6 UI approval and enforced handoff validation remain unverified. Record version/config and distinguish verified behavior from planned behavior.
- The repository is past initial bootstrap; a role branch is a collaboration lane, not a permanent owner lock. Integrate through small PRs to `main`.

## Collaboration lanes
- `work/orchestration`: orchestration lead owns `omnigent/`, `agents/`, and `policies/`; completes enforced handoff validation, wires agents to ledger events, and verifies P6 in the UI before experiment execution is treated as approved.
- `work/science`: science + planner owns question selection, `tools/openml_run.py`, experiment runner, `core/beliefs.py`, prediction/surprise/planner scoring, and Analyst contracts. Lock the question and metric early and announce the contract before downstream work.
- `work/benchmark`: benchmark + rigor owns `bench/`, baseline single-agent arm, metric definitions, seeds/error bars, `tools/citation_check.py`, top-finding novelty check, README claims/limits, submission and next-experiment write-up. Start with metric definitions and baseline harness; synchronize with science on the locked question.
- `work/core-ui`: the lane covers `core/ledger.py`, `schemas/`, `server.py` (SSE), `cli/`, and `ui/`, but contributors may split core/CLI and frontend UI work by agreement. Build consumers against the fake event generator. Keep the UI focused on the research use case and use the room metaphor with simple animated SVG mascots; pixel-art assets are not required. Make Omnigent visible as the underlying runtime/policy layer, not as a substitute for demonstrating the scientific workflow.
- Any contributor may fix bugs outside their lane after coordinating with the lane owner. Role lanes do not grant exclusive write rights.

## Contracts that must stay stable
1. `schemas/event.schema.json` is the producer/consumer boundary. Coordinate changes before changing event names or required fields.
2. All agent handoffs are structured JSON validated at the boundary; preserve raw input and validation errors for audit. Invalid payloads must not proceed as valid decisions.
3. Ledger events are append-only, timestamped, run-scoped, and include `seq`, `run_id`, `agent`, `type`, `payload`, `ai_generated`, `prev_hash`, and `hash` (see schema). UI and CLI read events; agents never write directly to UI state.
4. Before compute, store prediction, falsifier, metric, seed, and experiment plan. Record dataset/version, code hash, environment, cost/time, result, uncertainty, and next decision.
5. Mark generated hypotheses and agent-authored conclusions as AI-generated. Distinguish source-backed facts, inferences, and unverified suggestions.

## Working agreement
- Start from updated `main`, work on the matching `work/*` branch, and keep commits focused. Never force-push shared branches.
- Before editing a shared contract or another lane's files, coordinate in the team chat and describe the compatibility impact. Prefer additive schema changes.
- Each PR states: problem, changed files/contracts, run commands and observed output, limitations, and follow-up owner. Merge only through reviewed PRs into `main`.
- Put decisions and handoff notes in `docs/coordination/`; include owner, date, status, interfaces, blockers, and next action. Do not rely on chat as the only record.
- Keep `main` runnable. Do not check in credentials, local databases, unreviewed raw model output, or fabricated benchmark numbers.
- No benchmark claim without a documented baseline, denominator, repetitions, seeds where applicable, uncertainty, cost, and raw result artifacts. If runs are too few, label results preliminary.
- Run only the checks necessary for the change and report exactly what ran. Do not claim a test or verification that did not run.

## Safety and scientific integrity
- Experiments are computational and use approved datasets/tools only. Apply resource limits and network allowlists to execution workers where supported.
- Require human approval for risky or externally consequential actions and final recommendations. A denial/approval record belongs in the ledger.
- Novelty verdicts are search results, not proof of novelty. Report KNOWN/CONTRADICTED/uncertain findings honestly and preserve prior-art links.
- Do not describe model-generated hypotheses as discoveries. Report replication, null results, disagreements, missing evidence, and limits.

## Agent startup checklist
1. Read this file and `docs/PROJECT_PLAN.md`.
2. Check `git status --short --branch`; do not overwrite uncommitted teammate work.
3. Identify your lane and inspect its current branch/coordination note.
4. Confirm relevant schemas and existing interfaces before implementing.
5. Record decisions, checks, results, and blockers in your PR or coordination note.
