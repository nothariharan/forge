# FORGE UI direction and demo contract

Status: **not implemented**. The core/UI lane should build from `core/fake_events.py` and `core/ledger.py`; the UI must not depend on live agents to render a complete demo.

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
