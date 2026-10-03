# Omnigent feasibility smoke test

Status: **not run**. Owner: orchestration lead (confirm).

Record exact date, Omnigent repository and commit/release, Python/runtime and Claude Code versions, operating system, commands, config, outputs, and failures. Do not paste credentials or tokens.

## Required checks

1. Install/run the upstream-supported minimal setup from a clean checkout.
2. Start two specialist Claude Code harness instances under Omnigent.
3. Pass one schema-valid structured object from agent A to agent B and preserve trace/log IDs.
4. Submit one deliberately invalid handoff and confirm it is blocked or explicitly rejected.
5. Trigger one real policy denial (for example, budget cap or unapproved action) and confirm enforcement is outside prompt-only behavior.
6. Determine how to observe lifecycle/handoff/policy events and map them to FORGE ledger events.
7. Document sandbox, network, account, model and concurrency limitations.

## Result template

- Commit/release:
- Environment:
- Setup command/result:
- Handoff command/result:
- Invalid payload result:
- Policy denial result:
- Event/log interface:
- Limitations:
- Continue with Omnigent? If not, what failed and what remains a rubric risk:
