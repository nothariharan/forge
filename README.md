# FORGE

**FORGE** is a planned computational scientific discovery lab for Hack-Nation × Databricks Track 03. Its central goal is to measure whether a structured, tool-using, multi-agent harness improves the quality or throughput of a reproducible research loop over a single-agent baseline.

The intended loop is **question → evidence → hypothesis → preregistered experiment → result → updated decision**. Agent-generated hypotheses are labeled as such. Findings are provisional and require appropriate expert validation.

## Project status

This repository is at setup stage. The domain (AI/ML research with OpenML), architecture details, Omnigent integration, and evaluation protocol are proposals pending smoke tests and an explicit science question. No performance results are claimed yet.

## Start here

- [Contributor and agent guide](AGENTS.md)
- [Implementation plan and decision gates](docs/PROJECT_PLAN.md)
- [Coordination board](docs/coordination/WORKSTREAMS.md)
- [Original technical design](docs/source/forge-technical-design.md)
- [Source documents and provenance](docs/SOURCE_INDEX.md)

## Work lanes

- `work/orchestration` — Omnigent, specialist agents, policies
- `work/science` — scientific question, experiment tool, beliefs and planner
- `work/benchmark` — baseline, metrics, rigor and submission evidence
- `work/core-ui` — schemas, ledger, event server, CLI and floor UI

Branches are shared work lanes. Merge reviewed pull requests into `main`; coordinate changes to `schemas/event.schema.json` before editing.

## Planned quick start (commands will be finalized with implementation)

```text
forge init
forge run "<locked research question>" --budget <limit>
forge status
forge tail
forge bench "<locked research question>"
forge verify <run_id>
```

See the implementation plan for phase gates. The project is not yet runnable.
