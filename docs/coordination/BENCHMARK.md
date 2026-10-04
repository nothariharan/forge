# Benchmark lane: status and interfaces

- **Owner:** Akshat
- **Branch:** task branches from `main` (latest: `bench/run-bench`)
- **Status:** protocol draft v0.1, citation checker, report generator, oracle sweep and arm A tools ready; arm A writes through the shared ledger. The science question is not locked (see `BENCHMARK_TESS_GATE_REVIEW.md`), so the protocol and baseline prompt stay drafts. No matched A-vs-B benchmark has been run.

## Done

- `bench/PROTOCOL.md`: arms, metrics with numerators/denominators, budget, seeds, oracle, analysis, failure handling, artifact layout. Question-dependent fields are marked TBD (science).
- `tools/citation_check.py`: resolves DOI / arXiv / OpenAlex IDs / URLs and checks quoted spans against the abstract or a supplied full text. Resolution and quote support are reported separately (protocol S3/S4). Network errors are counted separately and never as "unresolvable".
- `bench/report.py` + `bench/stats.py`: compute every metric from episode artifacts; paired bootstrap, Wilson and Clopper-Pearson intervals; standard library only.
- Tests: `python3 -m pytest -q tests/` (needs `pytest`; `citation_check.py` needs `requests` for live use).

## Interfaces this lane depends on

### Event payload keys (for Ish, core/UI; and Saksham, orchestration)

`bench/report.py` reads these keys from `payload` in `schemas/event.schema.json` events. These keys are implemented in the merged shared schemas; coordinate before changing them:

| Event | Payload keys used |
|---|---|
| `PREDICTION_COMMITTED` | `eid` |
| `RUN_STARTED` | `eid`, `hid`, `candidate` (optional; the configuration being tested) |
| `RUN_FINISHED` | `eid`, `status` (`"ok"` or a failure value), `metrics` (`{metric_name: value}`) |
| `HYPOTHESIS_PROPOSED` | `hid` |
| `REPLAN` | `trigger_eid` (the result that caused the replan) |
| `GATE_OPENED` / `GATE_RESOLVED` | `gate_id` |

Also used: `RUN_CREATED` and `RUN_COMPLETED` timestamps mark the timed window.

### Experiment runner (for Hari)

`bench/oracle.py` calls the runner as `run(task_id, params: dict, seed: int) -> {"metrics": {name: value}, ...}`, configured as `"runner": "tools.openml_run:run"` in the sweep spec. If `tools/openml_run.py` ends up with a different signature, tell me and I'll adapt `oracle.py`, or we add a thin wrapper.

### Shared ledger payload schemas (with Ish, PR #4)

`bench/arm_a.py` payloads now satisfy the per-event schemas in `schemas/*.json` from PR #4, and an arm A episode imports into `core/ledger.py` with `validate_payloads=True` and verifies (checked on a local merge of `work/core-ui`, `work/science` and `work/benchmark`: 55 tests passed). Resolutions of the table in `CORE_UI.md`:

| Event | Resolution |
|---|---|
| `PREDICTION_COMMITTED` | arm A adopts the schema: `hid`, `metric`, `mean`, `sd` (> 0), plus `eid` and `falsifier`. No need to loosen the schema. |
| `HYPOTHESIS_PROPOSED` | arm A adds `prediction`, `falsifier`, `prior`, the same fields FORGE's Hypothesizer must give. |
| `RUN_STARTED` / `RUN_FINISHED` | arm A adds `hid`, `code_hash` (sha256 of the runner source), `data_ver` (set at `init`, e.g. `openml:1590@2`) and `seed`. Event `metrics` keep numeric values only; lists such as per-fold scores stay in `run_records.jsonl`. |
| `REPLAN` | arm A adds `reason` and `reopened`, keeps `trigger_eid`. |
| `FINDING` | arm A no longer emits it for an unchanged plan; those decisions go to `decisions.jsonl`. |
| `RUN_COMPLETED` | arm A adds `status: "completed"`. |
| `quote_span` vs `quote` | `tools/citation_check.py` accepts both, and `text` as the claim, so evidence claims can be passed in unchanged. |

`tests/test_arm_a.py::test_payloads_pass_shared_payload_schemas` validates every Arm A event with `core.schemas`.

**Arm A now writes through `Ledger.append` (2026-10-04).** Each command appends via `core/ledger.py`, so validation, seq/prev_hash assignment and hashing are the same code FORGE uses; an invalid payload is rejected before anything is written. After every append the run is re-exported to the episode's `events.jsonl`, which `bench/report.py` reads. Each episode has its own `<episode>/ledger.db` by default; `init --ledger results/ledger.db` writes into a shared ledger instead, so the UI/CLI can follow a baseline run. Arm A also fills the optional `refs` field (`hid`, `eid`). Checked: an episode verifies with `python -m cli.verify --db <episode>/ledger.db <run_id>`.

### Arm B (FORGE) episode contract (for Saksham)

`bench/launch_arm_b.py` runs FORGE headless (`omni run omnigent/forge --no-session -p <task message>`) with `FORGE_LEDGER_DB` set to the episode ledger. The task message starts with `Run id: <id>` and repeats arm A's question, task, budget and research rules verbatim.

The harness itself:
- records `RUN_CREATED` (opens the timed window);
- enforces the wall clock;
- closes the episode if FORGE does not;
- exports `events.jsonl`.

For the comparison to be fair and scorable, FORGE's events need:

| Need | Why | Status in `orch/ledger-handoff` |
|---|---|---|
| `RUN_COMPLETED` payload includes `"candidate": "<id>"` | That is FORGE's scored answer (saved as `answer.json`) | Director records `status` and `summary` only; please add `candidate` |
| `PREDICTION_COMMITTED` with `eid` before each experiment | Otherwise every FORGE run counts as a preregistration violation (S7) and is not a valid experiment | Not recorded yet |
| `RUN_FINISHED` with `eid`, `status`, `metrics` (and `candidate` if no `RUN_STARTED`) | Attempts and valid experiments are counted from it | Recorded by the experimenter |
| Experiment cap = spec `max_experiments` | Matched budget; arm A's cap is enforced by `arm_a.py` | P2 caps all dispatches at 3, not experiments |
| Token / USD usage per episode (`usage.json`) | Cost metrics (S9); without it they read n/a for both arms | Not available for either arm yet. Does Omnigent expose usage? |

`bench/report.py` now counts a run seen only as `RUN_FINISHED` as an attempt, using it for the preregistration check, so FORGE runs are counted even without `RUN_STARTED`.

### Science contract (for Hari)

The open questions are listed in `bench/PROTOCOL.md` section 13. First review whether the Adult missingness question has enough scientific value; then lock task, metric and threshold, candidate space for the oracle sweep, primary outcome, budget values, and seed handling in `tools/openml_run.py` with Hari.

### Baseline arm (for Akshat)

Arm A must run with the same model, tools and sandbox limits as FORGE. `bench/arm_a.py` writes through `core/ledger.py`.

**Launcher (`bench/launch_arm_a.py`, 2026-10-04):**
- Fills `bench/baseline_prompt.md` from a spec file and refuses to start if any placeholder has no value.
- Runs `arm_a.py init` with the budget written into the manifest. `arm_a.py` then refuses runs beyond `max_experiments`, refuses runs or answers after the deadline, and refuses anything after the episode is closed.
- Writes a one-agent Omnigent config using only fields verified in `OMNIGENT_SMOKE_TEST.md` (`spec_version: 1`, `claude-sdk`, `caller_process`, prompt), with no sub-agents and no policy gates.
- Runs the agent in its own process group with a hard timeout at the wall-clock budget plus 30 s grace, and stops the whole group on timeout.
- Closes an episode without an answer as `budget_exhausted` (deadline) or `aborted` (agent exited early), so it stays in every denominator.
- Writes `prompt.md`, `omni_agent/config.yaml`, `agent_stdout.log`, `agent_stderr.log` and `launcher.json` into the episode folder.

**Headless command** (confirmed by Saksham, Omnigent 0.16.0, 2026-10-04): `omni run <agent_dir> --no-session -p "<filled prompt>" </dev/null`. This is the launcher's default:
- `--no-session` gives each episode a fresh temporary store, so episodes stay independent.
- The final answer goes to stdout (`agent_stdout.log`), and omni exits 0 on its own.
- The launcher always closes stdin.
- The filled prompt goes in via `-p`. The config's own `prompt:` is a short role line, so the task text is not sent twice (that would inflate arm A's token cost).
- The baseline config has no `ASK` policies: a headless run cannot answer an approval prompt and would die.
- Run `omni setup` once per machine first; the `claude-sdk` harness needs a Claude credential.

**Not verified here:** a real `omni run` of a generated config. `omni` is not installed in the environment this was built in. The first real episode on a machine with `omni setup` done is the check.

`bench/baseline_prompt.md` was reviewed independently by Hari (2026-10-04): balanced for a solo arm, no oracle hints, question/budget/tools/scoring laid out fairly. **Not freeze-ready:** it still assumes an OpenML task and a single candidate recommendation, so it stays a draft until the science question is locked and the prompt is adapted to it.

## Blockers

- The resolver APIs (`api.openalex.org`, `export.arxiv.org`, `api.crossref.org`) are blocked by the network policy of the cloud environment this lane was developed in. The checker is tested offline with stubbed responses only. It still needs a live run on a machine with normal internet access.

## Next actions

1. ~~Prior-art and value review~~ done for Adult, Kepler and TESS (`BENCHMARK_REVIEW_EXOPLANET.md`, `BENCHMARK_TESS_GATE_REVIEW.md`); waiting on Hari's TESS cross-match and Referee search.
2. With Hari, lock the question and protocol TBDs, including the bottleneck/denominator, candidate tests, budgets, primary metric, seeds and stopping rule.
3. ~~Migrate Arm A to `Ledger.append`~~ done; ~~independent prompt review~~ done (Hari). ~~Single-agent launcher~~ done (`bench/launch_arm_a.py`), pending one real `omni run` check. Still to do: adapting the prompt to the locked question.

**End-to-end runner (`bench/run_bench.py`):** one command runs arm A and arm B for every seed (alternating which arm goes first), builds the oracle if an oracle spec is given, and writes `report.md` / `report.json` with the throughput multiplier and its interval. Interrupted benchmarks resume, and failed launches are recorded in `bench_manifest.json`. Tested end to end with fake agents only. Do not run it for real until the protocol is frozen.
4. Validate the full OpenML runner before writing/running an oracle sweep. Then complete the matched comparison, uncertainty/cost analysis, citation/novelty checks, and next-experiment write-up.
