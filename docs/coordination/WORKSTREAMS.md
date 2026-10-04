# Workstream coordination board

This file is the repo-visible handoff board. Update status and interfaces in a PR or commit so contributors who join later can synchronize.

| Lane | Branch | Lead (confirm with team) | First deliverable | Current status |
|---|---|---|---|---|
| Orchestration | `work/orchestration` | Saksham (based on PR #5) | Omnigent graph, engine policy proof, event wiring | Partial smoke test merged; P6 UI verification, enforced handoff validation, and ledger wiring remain |
| Science + planner | `work/science` | Hari | Choose a worthwhile question after prior-art review; validate full runner and publish contract | Adult one-fold feasibility only; simple question overlaps prior work and local runner validation is blocked by Python environment |
| Benchmark + rigor | `work/benchmark` | Akshat | Assess candidate value, then freeze protocol with Hari; complete baseline and measured comparison plan | Protocol v0.1 and tooling exist; science-dependent fields, candidate-value review, independent prompt review, and Arm A `Ledger.append` migration remain |
| Core + CLI | `work/core-ui` | Ish | SSE server and `forge tail` / status / replay against the fake stream | Ledger/schemas/fake stream/verify CLI merged; SSE and broader CLI remain |
| Product UI | `work/core-ui` | To assign | Research-lab room view with SVG agent mascots, driven by fake/replay events | Direction and demo path documented in `ui/README.md`; implementation not started |

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
