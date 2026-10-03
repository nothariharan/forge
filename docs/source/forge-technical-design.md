# FORGE

A closed-loop scientific lab layered on Omnigent, with a live pixel lab floor and a CLI. Target: Hack-Nation x Databricks, Track 03. Hardened for the objections raised against Robin (rediscovery, hallucinated refs, unmeasured speedup).

## 0. Verify before building

- Repo is `omnigent-ai/omnigent` (Apache-2.0, alpha). Smoke-test a 2-agent handoff and one blocking policy **before kickoff**. Everything below assumes both work.
- Algorithm and paper citations below are from memory. Check each reference resolves before it goes in the submission. Our own citation policy (P1) would reject unverified ones.
- YAML and policy snippets are sketches of intent, not Omnigent's exact schema. Adapt to its docs.

## 1. Thesis

Discovery is slow because the loop *question, evidence, hypothesis, experiment, result, decision* is slow and leaky. FORGE makes each edge of that loop a checked, measured, logged handoff. Core claim, measured not asserted: **harness beats base model**, shown by running the same question through a single plain agent and through FORGE, and reporting the difference.

Chosen domain: **AI-research hypotheses on OpenML benchmarks** (fast, reproducible experiments, so the planner gets many loops and the bench numbers mean something). Swap domain by swapping the tool pack only.

## 2. Architecture

```
                +-----------------------------+
   CLI  --------|        forge-core           |-------- Floor UI (canvas)
 (forge ...)    |  FastAPI + SSE + SQLite     |   (reads events only)
                +--------------+--------------+
                               | append / subscribe
                      +--------v---------+
                      |  LEDGER (hash    |  single source of truth
                      |  chained events) |  replay, bench, audit
                      +--------^---------+
                               | events via hook/wrapper
                +--------------+----------------------------+
                |            OMNIGENT (orchestrator)        |
                |  sessions | parallel runs | policies | sandboxes
                +---+-------+--------+---------+-------+----+
                    |       |        |         |       |
               Librarian Hypothesizer Referee Planner Experimenter x N, Analyst x K, Safety
               (Claude Code harness instances, one prompt+policy file each)
                    |                                  |
              OpenAlex, arXiv, STORM,            OpenML, sklearn/XGBoost,
              PaperQA2 (lit tools)               sandboxed code execution
```

**Rule:** agents never talk to the UI. They emit events; the UI and CLI only read the ledger. That is what makes replay, benchmarking and the demo fallback free.

## 3. Agents (each owns one decision)

| Agent | Decision owned | Tools | Output contract |
| --- | --- | --- | --- |
| Librarian | What the literature supports | OpenAlex, arXiv, STORM, PaperQA2, Undermind (baseline) | `EvidencePacket{claims[], refs[doi\|arxiv], quote_span}` |
| Hypothesizer | Candidate hypotheses (labeled AI-generated) | evidence packets, Scientific Agent Skills | `Hypothesis{id, claim, prediction, falsifier, prior}` |
| Referee | NOVEL / KNOWN / CONTRADICTED | OpenAlex, arXiv search, debate with Hypothesizer | `NoveltyVerdict{hid, label, prior_art[]}` |
| Planner | Which experiment to spend budget on | belief store, cost model | `ExperimentSpec{eid, hid, design, est_cost, EIG}` |
| Experimenter xN | Run it, reproducibly | sandbox, OpenML, sklearn/XGBoost | `RunRecord{eid, code_hash, data_ver, seed, metrics}` |
| Analyst xK | What the result means (independent trajectories) | stats libs, notebooks | `Finding{eid, effect, ci, verdict}` per trajectory, then consensus |
| Safety | Block or escalate risky actions | policy engine, approval queue | `Gate{action, risk, status: pending\|approved\|denied}` |

Each agent is a Claude Code harness instance with its own prompt file (`agents/*.md`) and policy file (`policies/*.py`). Handoffs carry structured JSON validated against schemas in `schemas/`; an invalid payload is rejected and bounced back, not forwarded.

## 4. Algorithms (the "unique" part)

### 4.1 Pre-registered predictions and surprise

Before running, the Hypothesizer commits `prediction` and `falsifier`; the ledger stores the hash and timestamp. After the run, surprise is the divergence between the committed predictive distribution and the observed result:

```
surprise = -log p_prior(observed)        # or KL(posterior || prior) after update
if surprise > tau: emit SURPRISE -> Planner must reopen parent assumptions
```

This is the mechanical definition of "the result changed the next decision", and it drives the alarm and replan on the floor.

### 4.2 Bayesian experimental design planner

Keep a Beta (or Gaussian) belief per hypothesis. Score each candidate experiment by expected information gain per unit cost and pick under a budget:

```
EIG(e) = E_y[ KL( p(h|y,e) || p(h) ) ]       # estimate by Monte Carlo over predicted outcomes
score(e) = EIG(e) / est_cost(e)               # cost = tokens + compute seconds
choose argmax score(e) subject to remaining_budget
```

Rooted in Bayesian optimal experimental design (Lindley; modern computational work includes Marzouk's group at MIT). Fallback if EIG is too heavy: Thompson sampling over hypothesis beliefs with successive halving to cut losers early.

### 4.3 Tournament ranking of hypotheses

Pairwise LLM-judge matches, fit with Bradley-Terry-Luce, as Robin did (round robin up to 25, else \~300 sampled pairs). Run each pair in both orders to cancel position bias. Use a different model family as judge than as generator.

### 4.4 Referee via multi-agent debate

Referee and Hypothesizer argue over novelty across 2 to 3 rounds, with prior-art retrieval allowed each round (debate idea from Du, Li, Torralba, Tenenbaum, Mordatch, MIT CSAIL, 2023). Verdict must cite prior art IDs. A KNOWN verdict is reported, not hidden.

### 4.5 Consensus analysis with agreement scoring

Run K=3 to 5 independent Analyst trajectories in parallel (Omnigent parallel runs). Accept a finding only if a majority agree on direction and CI overlap; report agreement as a number. Disagreement is itself an event and triggers a referee check.

### 4.6 Hash-chained ledger

```
entry.hash = sha256(prev_hash || canonical_json(entry_without_hash))
```

Tamper-evident, makes "reconstruct every decision" trivial, and `forge verify` checks the chain.

## 5. Omnigent policies (policy as code)

| ID | Policy | Effect |
| --- | --- | --- |
| P1 | Citation gate: every ref must resolve (DOI/arXiv via OpenAlex/arXiv API) and the quoted span must exist in the source | Deny handoff, bounce to Librarian |
| P2 | Budget cap: cumulative cost over limit | Deny new experiment, force Planner to stop or re-prioritize |
| P3 | Pre-registration: experiment cannot start without a committed prediction and falsifier | Deny run |
| P4 | Novelty gate: no compute on a hypothesis labeled KNOWN unless flagged as replication | Deny or reroute |
| P5 | Sandbox limits: no network from Experimenter except allowlisted data hosts; time and memory caps | Tool permission |
| P6 | Human approval: any "recommend" or final-claim action | Pause, create Gate, wait on `forge approve` or UI popup |

Enforce through tool permissions and Omnigent policies, not prompts. Show at least one real denial live in the demo.

## 6. Ledger event schema

```
{
 "seq": 412, "ts": "2026-10-..Z", "run_id": "r7",
 "agent": "planner", "type": "EXPERIMENT_SELECTED",
 "refs": {"hid":"H3","eid":"E9","parent":"E7"},
 "payload": {"candidates":[{"eid":"E8","eig":0.21,"cost":4.0},{"eid":"E9","eig":0.55,"cost":3.1}],
             "chosen":"E9","budget_left":38.2},
 "ai_generated": true,
 "prev_hash": "ab12...", "hash": "9f3c..."
}
```

Event types: `EVIDENCE_ADDED, HYPOTHESIS_PROPOSED, NOVELTY_VERDICT, PREDICTION_COMMITTED, EXPERIMENT_SELECTED, RUN_STARTED, RUN_FINISHED, FINDING, CONSENSUS, SURPRISE, REPLAN, POLICY_DENIED, GATE_OPENED, GATE_RESOLVED`.

## 7. Floor UI

- **Stack:** single HTML page, plain 2D canvas, tilemap, CSS or sprite-sheet characters (3 states: idle, walk, work). SSE from `forge-core`. No game engine.
- **Rooms:** Library (Librarian), Whiteboard (Hypothesizer + hypothesis graph), Peer Review (Referee), Bench (Experimenters), Analysis Desk, Safety Desk, PI Office (you).
- **Event to animation map:** HYPOTHESIS_PROPOSED = agent walks to whiteboard, node appears. EXPERIMENT_SELECTED = Planner points at bench, carries a packet with `eid`. SURPRISE = alarm, whiteboard wipes the parent branch, agents converge in meeting area (REPLAN). GATE_OPENED = Safety agent knocks on PI Office, popup with Approve / Deny. POLICY_DENIED = red flash at the offending agent's desk.
- **Side panel:** belief bars per hypothesis, budget gauge, live event log, bench counter.
- **Replay:** same renderer driven from the stored ledger at adjustable speed. This is the demo fallback.
- **Time cap:** about 6 hours total. Cut order: sprite polish, sound, extra rooms.

## 8. CLI

```
forge init                     # scaffold, check Omnigent
forge run "question" --budget 40   # start a lab session
forge status                   # beliefs, budget, open gates
forge tail                     # live event stream
forge approve|deny <gate_id>
forge replay <run_id> --speed 4
forge verify <run_id>          # hash-chain + citation re-check
forge bench "question"         # baseline vs FORGE, prints the table
forge ui                       # serve floor on localhost
```

## 9. Bench: the measured speedup

Same question, same budget, two arms: **A** single plain Claude Code agent, **B** full FORGE. Optional arm **C**: Undermind or a deep-research tool for the literature step only. Report with denominators and cost:

| Metric | A | B |
| --- | --- | --- |
| Hypotheses tested per hour | ? | ? |
| Hallucinated or unresolvable refs (%) | ? | ? |
| Experiments needed to reach top candidate | ? | ? |
| Hypotheses later labeled KNOWN (%) | ? | ? |
| Cost ($ / tokens) and wall time | ? | ? |

Run N≥3 seeds per arm and show error bars. Report the multiplier you actually get, 1.5x included. Ablations to add if time: drop Referee, drop Planner (random order), drop consensus; show each costs something.

## 10. Open-source reuse

| Tool | Use |
| --- | --- |
| Omnigent | Orchestrator, sessions, parallel runs, policies, sandboxes |
| Claude Code | Harness for every agent |
| stanford-oval/storm | Cited literature briefs for the Librarian; do not rebuild |
| PaperQA2 (FutureHouse) | Grounded paper QA with citations, as used in Robin |
| Scientific Agent Skills (arXiv 2609.00065) | Procedural skills for analysis (rigor); load only what the task needs |
| OpenAlex, arXiv, OpenML | Literature graph, papers, datasets and benchmark tasks |
| FastAPI, SQLite, sklearn, XGBoost | Core, ledger, experiments |

## 11. Repo layout

```
forge/
  agents/        librarian.md hypothesizer.md referee.md planner.md experimenter.md analyst.md safety.md
  omnigent/      lab.yaml (agent graph), policies/ p1_citations.py ... p6_approval.py
  schemas/       evidence.json hypothesis.json spec.json run.json finding.json gate.json
  core/          ledger.py (hash chain) beliefs.py (EIG, surprise) tournament.py (BTL) server.py (SSE)
  tools/         openalex.py arxiv.py openml_run.py citation_check.py
  cli/           forge.py
  ui/            index.html floor.js sprites/
  bench/         arms.py report.py
  results/       runs/*.jsonl  figures/
  README.md      reproduce in 3 commands
```

## 12. 24-hour plan

| Hours | Work | Exit check |
| --- | --- | --- |
| Pre | Omnigent 2-agent handoff + one denial; one OpenML experiment by hand | Both work |
| 0-4 | Lock question and metric; schemas; ledger + hash chain; stub events | `forge tail` shows a fake run |
| 4-10 | Librarian, Hypothesizer, Planner (EIG), Experimenter; P1, P2, P3 | One real loop end to end |
| 10-14 | Referee debate, Analyst consensus, Safety gate (P6); surprise triggers replan | A result changes the next experiment |
| Parallel (UI owner) | Floor on stub events from hour 2, swap to real events at hour 10 | Replay works |
| 14-20 | `forge bench`, seeds, ablations, novelty check on top finding | Table with denominators |
| 20-24 | Record 2-min demo, README, next-experiment writeup, limits | Submission checklist |

## 13. Two-minute demo script

1. (0:00) Question appears on the whiteboard; Librarian walks to Library and returns with cited evidence.
2. (0:25) Hypotheses appear labeled AI-generated; Referee marks one KNOWN and it is dropped.
3. (0:45) Planner shows two candidate experiments with EIG per cost, picks one; prediction is committed.
4. (1:05) Result arrives, SURPRISE alarm, whiteboard wipes a branch, team replans.
5. (1:25) A policy denial (bad citation or budget) shown live; approval knock at the PI Office.
6. (1:40) Bench table: measured multiplier, error bars, cost. State the next experiment and what validation is still needed.

## 14. Risks and honesty rules

- Omnigent is young; keep ledger and schemas independent of it so a fallback runner can replay the same events.
- If the top finding is a rediscovery, say so. That is rigor.
- No claim of 10x. Report the observed multiplier, its baseline, sample size and cost.
- Label every agent-generated hypothesis; state validation still needed (real-world or wet-lab) in the writeup.
- Do not claim these experiments prove a discovery; they show the lab's loop produces evidence that changes the next decision.