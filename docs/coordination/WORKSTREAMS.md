# Workstream coordination board

This file is the repo-visible handoff board. Update status and interfaces in a PR or commit so contributors who join later can synchronize.

| Lane | Branch | Lead (confirm with team) | First deliverable | Current status |
|---|---|---|---|---|
| Orchestration | `work/orchestration` | To confirm | Omnigent version/config check, 2-agent handoff and policy denial | Ready to start |
| Science + planner | `work/science` | Hari (proposed by requester) | Lock question/task/metric and run one deterministic experiment | Ready to start |
| Benchmark + rigor | `work/benchmark` | Akshat (proposed by requester) | Protocol, metrics and baseline runner | Ready to start; depends on science contract |
| Core + UI + CLI | `work/core-ui` | Ish (proposed by requester) | Event schema/fixture and fake generator/replay skeleton | Intentionally begins against agreed fake-event contract |

Names are inferred from the supplied chat excerpt and should be confirmed by the team. Work can move between people as needed. Branch ownership never prevents collaboration.

## Shared interfaces

- Event contract: `schemas/event.schema.json` (bootstrap version; coordinate before incompatible changes).
- Example event stream: `schemas/examples/sample-run.jsonl`.
- Science experiment contract: `schemas/experiment.schema.json` and `docs/coordination/SCIENCE_CONTRACT.md`.
- Omnigent findings: `docs/coordination/OMNIGENT_SMOKE_TEST.md`.

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
