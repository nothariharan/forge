# Omnigent feasibility smoke test

Status: **pass** (2026-10-04): full seven-agent loop verified live in run live-exo-8. Owner: Saksham (orchestration).

## Environment

- Omnigent 0.16.0, installed with `curl -fsSL https://omnigent.ai/install.sh | sh` (a `uv tool install` of the PyPI wheel, Python 3.12)
- macOS (Darwin 25.5), Node 25, tmux 3.x
- Credentials: Claude subscription (`claude-sdk` harness) and ChatGPT subscription (`codex` harness), configured with `omni setup`. No API keys in the repo.

## Config format (verified against the installed package, not guessed)

- An agent is a **directory** containing `config.yaml` with `spec_version: 1`. A single YAML file that declares `spec_version` is rejected.
- Sub-agents live in `agents/<name>/config.yaml` and are listed under `tools: agents:` in the parent.
- The lead dispatches with `sys_session_send(title, message)`, ends its turn, and is woken when the sub-agent finishes. It reads results with `sys_read_inbox`.
- Policies go under `guardrails: policies:` as `type: function` with `on: [tool_call]`. A policy returns `ALLOW`, `DENY` or `ASK` (human approval).
- The builtin CEL policy (`omnigent.policies.builtins.cel.cel_policy`) needs no Python on our side and can keep counters in `session_state` via `state_updates`. Custom Python policies are imported with plain `importlib` in the server process, so they would need to be on that process's `PYTHONPATH`. That's why I used CEL here.

## Results

| Check | Result | Evidence |
|---|---|---|
| 1. Install and run | PASS | `omni run hello` returned the expected token |
| 2. Two agents, different harnesses | PASS | Claude director → Codex worker, reply came back through the inbox (`HANDOFF_OK 391`) |
| 3. Structured handoff | PASS (prompt-level) | 3 librarian runs each returned a valid `EvidencePacket` JSON (keys checked by the director) |
| 4. Invalid handoff rejected | **PASS** | `tools/forge_emit.py` validates against the ledger schema and writes an `ERROR` with the raw input instead; Omnigent's `handoff_gate_*` policies then deny the next `sys_session_send` (`Denied by policy: handoff gate: last handoff failed ledger schema validation`). Live run, ledger chain verified |
| 5. Real policy denial | **PASS** | P2: cap of 3 dispatches. Dispatches 1-3 allowed, #4 returned `Denied by policy: P2 budget: dispatch cap (3) reached for this run`. Enforced by the Omnigent policy engine, not the prompt |
| 5b. Human approval (P6) | **PASS** | Omnigent's native ASK cannot be answered in scripted runs (sub-agents are headless: live-exo-4; root ASK needs an attached client: live-exo-5). P6 is enforced by `tools/forge_gate.py`: the experiment command blocks until GATE_RESOLVED is written by the lab UI Approve button or `python -m cli.approve`. Verified live in **live-exo-8**: human approval at seq 9, then the real T1 run (AUC 0.7616, 95% CI [0.750, 0.774]), 13 events, chain OK. Benchmark runs set FORGE_GATE_MODE=auto, logged as `harness`, never as a human |
| 6. Events → ledger | **PASS** | Director records RUN_CREATED, each specialist result, POLICY_DENIED and RUN_COMPLETED through `Ledger.append` (via forge_emit). Live run wrote 4 events, `verify` = OK |
| 7. Tool permission (P5) | **PASS** | Director shell limited to `tools/forge_emit.py`, no chaining; `ls` → `Denied by policy: director shell is limited to tools/forge_emit.py` |

## Observations

- Self-reported `verified` flags are unreliable. Three librarian runs cited the same sources; one marked them `verified: false`, two marked them `true`. Use `tools/citation_check.py`, never the agent's own flag.
- The `claude-sdk` harness inherits the user's own Claude Code MCP config (the director reported a context7 auth warning). Harmless, but runs aren't hermetic.
- The interactive REPL exits when stdin closes, so headless `-p` runs can cut a turn short. For scripted runs, use the local server (`--server local`) and read the session there.

## How to run

```bash
omni run omnigent/forge
```

Continue with Omnigent? **Yes.** Multi-harness handoff and engine-enforced denial both work.

## Live findings (2026-10-04 afternoon)

- Root `guardrails` apply to every sub-agent Omnigent spawns: the director's shell allowlist blocked the experimenter (live-exo-3). P5 now lists the approved FORGE tools for all agents.
- The handoff gate caught a schema violation in a live run (`seed: '0-4'`) and the engine blocked the next dispatch (live-exo-7).
- Full loop in live-exo-8: librarian → hypothesizer → referee → planner (PREDICTION_COMMITTED before RUN_STARTED) → safety gate → human approval in the lab UI → experimenter (real T1 script on the NASA archive) → analyst FINDING + REPLAN → RUN_COMPLETED.
- P2 now caps 60 dispatches and 10 experiments per run; RUN_COMPLETED carries `candidate` for bench scoring.

## Harness choice for the benchmark (2026-10-04, 16:00)

All seven specialists and the director now run on `claude-sdk`. Earlier live runs (live-exo-3 to live-exo-8) used `codex` for the hypothesizer, planner and analyst; that showed Omnigent mixing harnesses, but it would confound the matched benchmark (arm A is a single claude-sdk agent; `bench/launch_arm_b.py` pins the same `ANTHROPIC_MODEL` for both arms) and codex is not installed on every teammate's machine. Raised by Ish.
