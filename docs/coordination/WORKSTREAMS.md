# Workstream coordination board

This file is the repo-visible handoff board. Update status and interfaces in a PR or commit so contributors who join later can synchronize.

| Lane | Branch | Lead (confirm with team) | First deliverable | Current status |
|---|---|---|---|---|
| Orchestration | `work/orchestration` | Saksham (based on PR #5) | Omnigent graph, engine policy proof, event wiring | Partial smoke test merged; P6 UI verification, enforced handoff validation, and ledger wiring remain |
| Science + planner | `work/science` | Hari | Resolve exoplanet outcome-label semantics, define an object-disjoint cohort, and complete prior-art review | Astronomy is a provisional product context only; precision-transfer metrics were withdrawn; corrected NASA audit is descriptive only |
| Benchmark + rigor | `work/benchmark` | Akshat | Independently review target, cohort/split and metric; freeze protocol only after science contract is valid | Protocol v0.1 remains draft; do not use the withdrawn exoplanet scores; independent baseline-prompt review and Arm A `Ledger.append` migration remain |
| Core + CLI | `work/core-ui` | Ish | SSE server and `forge tail` / status / replay against the fake stream | Ledger/schemas/fake stream/verify CLI merged; SSE and broader CLI remain |
| Product UI | `work/core-ui` | Saksham (proposed; coordinate with orchestration work) | Research-lab room view with SVG agent mascots, driven by fake/replay events | UI is not implemented. Can start with provisional astronomy context and generic replay; must label fixtures and avoid displaying withdrawn precision/planet-truth claims |

Owners reflect the current team allocation and can change as work shifts. Confirm new assignments in team chat and record them here. Branch ownership never prevents collaboration.

## Shared interfaces

- Event contract: `schemas/event.schema.json` (bootstrap version; coordinate before incompatible changes).
- Example event stream: `schemas/examples/sample-run.jsonl`.
- Science experiment contract: `schemas/experiment.schema.json` and `docs/coordination/SCIENCE_CONTRACT.md`.
- Omnigent findings: `docs/coordination/OMNIGENT_SMOKE_TEST.md`.
- UI and demo requirements: `ui/README.md`.

## Daily handoff template

```md
### YYYY-MM-DD / lane
- Owner:
- Branch / commit:
- Done:
- Interface or files changed:
- Commands/checks and observed result:
- Blocker / decision needed:
- Next action and owner:
```
