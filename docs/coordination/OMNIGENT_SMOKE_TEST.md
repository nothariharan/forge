# Omnigent feasibility smoke test

Status: **partial pass** (2026-10-04). Owner: Saksham (orchestration).

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
| 4. Invalid handoff rejected | NOT DONE | Validation is prompt-level only (`HANDOFF_INVALID`). Still needed: an enforced validator on the handoff boundary |
| 5. Real policy denial | **PASS** | P2: cap of 3 dispatches. Dispatches 1-3 allowed, #4 returned `Denied by policy: P2 budget: dispatch cap (3) reached for this run`. Enforced by the Omnigent policy engine, not the prompt |
| 5b. Human approval (P6, `ASK`) | UNVERIFIED | In a headless run the experimenter loaded the shell tool and the marker command never executed, but the run ended when the REPL's stdin closed, so it is not yet clear whether `ASK` paused the call. Next: confirm the approval card in the web UI |
| 6. Events → ledger | NOT DONE | Next PR: map dispatch / result / policy decisions to `core/ledger.py` events |

## Observations

- Self-reported `verified` flags are unreliable. Three librarian runs cited the same sources; one marked them `verified: false`, two marked them `true`. Use `tools/citation_check.py`, never the agent's own flag.
- The `claude-sdk` harness inherits the user's own Claude Code MCP config (the director reported a context7 auth warning). Harmless, but runs aren't hermetic.
- The interactive REPL exits when stdin closes, so headless `-p` runs can cut a turn short. For scripted runs, use the local server (`--server local`) and read the session there.

## How to run

```bash
omni run omnigent/forge
```

Continue with Omnigent? **Yes.** Multi-harness handoff and engine-enforced denial both work.
