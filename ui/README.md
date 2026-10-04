# FORGE UI direction and demo contract

Status: **implemented** (Lab Floor v1, see below). Read-only over the ledger; its only write is a human decision on a P6 gate (POST /api/approve). Replays work offline; live runs stream through `ui/live_server.py`.

## Provisional science context (2026-10-04)

The team is using NASA Kepler/TESS catalog vetting as a provisional story context while the science question is reviewed. The existing exoplanet precision-transfer result was invalidated: a catalog `CANDIDATE` status is not confirmed-planet truth, and the old “temporal” evaluation reused training objects. The current corrected artifact is a catalog disposition audit only. No exoplanet classifier result is approved for display.

The UI may start with the generic replay/event flow and astronomy-themed labels. Keep the statuses distinct (`CANDIDATE`, `CONFIRMED`, `FALSE POSITIVE`, `UNKNOWN`), show source/snapshot provenance, and label fixture values as demo data. Do not turn status counts into planet prevalence/precision or present candidate ranking as validated. The science owner will update this section once a valid outcome, holdout cohort, and metric are approved.

## What the demo needs to prove

FORGE is a research lab in which a question moves through evidence, hypothesis, preregistration, experiment, analysis and a changed (or explicitly unchanged) next decision. Make that one concrete workflow the main story. A judge should be able to see what each agent contributed, what evidence supports a claim, what was predicted before an experiment, what the run measured, and why the next decision changed.

Show Omnigent as the underlying runtime: identify the active harnesses, show specialist handoffs, and make policy decisions (including P2 denial and P6 human approval) visible. Keep the distinction clear: Omnigent composes and governs agents; FORGE provides the scientific workflow, experiment records, and reviewable research UI. Never imply an unverified policy or live agent behavior is active. Label fixture/replay data as demo data.

## Visual direction

- Keep the lab/room metaphor from the reference, but render it as a clean, modern vector interface. Use a small number of legible work areas (literature, hypotheses, experiment bench, analysis/replanning) as navigation or a light spatial overview; the room is a map of the workflow, not a detailed game scene.
- Use simple, friendly SVG agent mascots with subtle state animations (searching, thinking, running, waiting for approval, done). Avoid pixel art and sprite sheets. Each mascot is paired with a readable role label and textual status; animation is decorative and never carries essential information.
- Prefer a clear dashboard hierarchy: central lab/workflow canvas, a current run and approval panel, and a chronological event log. Keep citations, metrics, and run state readable at normal laptop size.
- Provide reduced-motion behavior and static status indicators. Use accessible contrast, keyboard-operable controls, and text labels for color-coded states.
- Do not make up event counts, significance, citations, approval outcomes, or experiment results. Use the ledger fixture and identify fabricated fixture content as replay/demo data.

## Data and interaction contract

- Treat validated ledger events as the source of truth. UI and CLI are read-only consumers of the ledger; they do not maintain a parallel run state.
- Support replay from the sample JSONL/fake event generator, then subscribe to live events through the SSE server when available. Display sequence/time so users can follow event order and reconnect/replay without gaps.
- At minimum, show run question/status/budget; agent role/status/current handoff; cited evidence; hypothesis and preregistered prediction/falsifier; experiment configuration and result; policy/human gate; analysis and next decision; and event history.
- Include a compact “Runtime” or “Architecture” detail view that names Omnigent and the active harnesses/policies without pulling attention away from the research workflow.

## Suggested demo path

1. Start with a clearly labeled saved run so the demo works offline.
2. Follow the Librarian evidence into a hypothesis and preregistered prediction.
3. Show an experiment request, its safety/approval state, and the recorded result.
4. Show analysis triggering a replan and explain the next action from the event log.
5. Open the Runtime detail to show Omnigent handoffs and policy enforcement, then return to the research view.

Avoid claiming scientific discovery or benchmark superiority from the UI. Those claims must come from the locked protocol and reproducible artifacts.

## Lab Floor (implemented, v0)

Static page, no build step. Read-only: it folds ledger events into the view and never keeps its own run state.

```bash
python3 -m http.server 8765        # from the repo root
# open http://localhost:8765/ui/                       replays ui/fixtures/exo-demo.jsonl
#      http://localhost:8765/ui/?src=../schemas/examples/sample-run.jsonl
#      http://localhost:8765/ui/?at=16                 jump to event 16, paused
#      http://localhost:8765/ui/?sse=<url>             live: EventSource, one event JSON per message (for Ish's SSE server)
```

- `ui/fixtures/make_exo_demo.py` writes the astronomy DEMO run (27 events) through the real `Ledger.append`, so it is schema-valid and hash-chained. Every payload has `"demo": true`; the question is marked not locked; ids, numbers and citations are placeholders; statuses stay distinct and no planet precision is shown.
- Views: Lab Floor (rooms, mascots, approval card, event log, overview), Experiments (planner candidates, EIG/cost, preregistration check, runs, denials), Hypotheses, Literature, Ledger (hash-link check), Benchmarks (honest "no result yet"), Runtime (Omnigent harnesses and policy status).
- The approval buttons are disabled: in replay the recorded decision follows, and in live mode approval happens in the Omnigent session (P6).

## Live wiring status (what is real vs stubbed)

| Piece | Status | Where |
|---|---|---|
| Omnigent director + librarian / hypothesizer / experimenter writing to the ledger | **wired** (each handoff goes through `tools/forge_emit.py`) | `omnigent/forge/` |
| UI following a live run | **wired via a temporary bridge**: `ui/live_server.py` streams `Ledger.subscribe` as SSE. Replace with the core lane's SSE server when it lands (`?sse=<url>`) | `ui/live_server.py` |
| Dynamic sub-agents | **wired**: any agent name in the ledger gets a mascot, matched to one of 15 archetypes by name (`ui/mascots.js`), generic dot otherwise | `ui/mascots.js` |
| Approve / Reject buttons | **wired**: banner + PI Office card POST to `/api/approve`, which writes GATE_RESOLVED; `tools/forge_gate.py` holds the experiment until then (verified in live-exo-8) | `ui/app.js`, `ui/live_server.py`, `tools/forge_gate.py` |
| Referee / planner / analyst / safety live agents | **wired**: all seven specialists run in Omnigent (claude-sdk + codex) | `omnigent/forge/agents/` |
| Policy denials from the engine itself | **partial**: the director records POLICY_DENIED after a denial; the engine does not write to the ledger directly. TODO: an Omnigent hook or session-export importer | `omnigent/forge/config.yaml` |

Run it live:
```bash
.venv/bin/python ui/live_server.py --port 8777 --db results/ledger.db
FORGE_LEDGER_DB=results/ledger.db omni run omnigent/forge -p "Run id live-1. <question>"
# open http://localhost:8777/ui/?run=live-1
```
