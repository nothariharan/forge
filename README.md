# FORGE

**FORGE** is a computational scientific discovery lab being built for Hack-Nation × Databricks Track 03. It makes a bounded research workflow visible: agents find evidence, propose a falsifiable hypothesis, run a reproducible computational experiment, inspect the result, and choose what to do next. Its central evaluation question is whether an Omnigent-orchestrated, tool-using multi-agent harness improves the quality or throughput of that loop over a matched single-agent baseline.

The intended loop is **question → evidence → hypothesis → preregistered experiment → result → updated decision**. Agent-generated hypotheses are labeled as such. Findings are provisional and require appropriate expert validation.

## Project status

The core event ledger, payload schemas, fake event stream, and Omnigent smoke-test graph are in `main`. A mixed-harness handoff and engine-enforced dispatch cap passed the documented smoke test; human approval in the UI and enforced handoff validation remain unverified. OpenML Adult task 7592 has a validated ten-fold runner and a one-seed exploratory candidate sweep, both feasibility-only. Astronomy/exoplanet catalog vetting is the provisional product context, not a locked research question. Its first classifier precision-transfer analysis was invalidated because candidate status is not confirmed-planet truth and the temporal evaluation reused training objects; the replacement archive audit reports catalog transitions only. No valid exoplanet model result or A-vs-B benchmark exists. See `docs/coordination/SCIENCE_DECISION_PACKET.md` before using science claims.

## Start here

- [Contributor and agent guide](AGENTS.md)
- [Implementation plan and decision gates](docs/PROJECT_PLAN.md)
- [Official Track 03 challenge brief](docs/references/reference-02.pdf)
- [Coordination board](docs/coordination/WORKSTREAMS.md)
- [Original technical design](docs/source/forge-technical-design.md)
- [UI direction and demo requirements](ui/README.md)
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

See the implementation plan for phase gates. Individual components and the ledger fixture can be run, but the complete FORGE workflow and product UI are not yet runnable end to end.
