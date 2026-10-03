# Benchmark lane: status and interfaces

- **Owner:** Akshat
- **Branch:** `work/benchmark`
- **Status:** protocol draft v0.1, citation checker, and report generator ready. The one-fold Adult run in `SCIENCE_CONTRACT.md` is feasibility-only, not benchmark evidence. No matched A-vs-B benchmark has been run.

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

`tests/test_arm_a.py::test_payloads_pass_shared_payload_schemas` validates every Arm A event with `core.schemas`; it is active after PR #4 merged.

### Science contract (for Hari)

The open questions are listed in `bench/PROTOCOL.md` section 13. First review whether the Adult missingness question has enough scientific value; then lock task, metric and threshold, candidate space for the oracle sweep, primary outcome, budget values, and seed handling in `tools/openml_run.py` with Hari.

### Baseline arm (for Akshat)

Arm A must run with the same model, tools and sandbox limits as FORGE. `bench/arm_a.py` already writes events in the shared schema format. It still needs to switch to `core/ledger.py` and have a launcher compatible with the Omnigent run setup.

## Blockers

- The resolver APIs (`api.openalex.org`, `export.arxiv.org`, `api.crossref.org`) are blocked by the network policy of the cloud environment this lane was developed in. The checker is tested offline with stubbed responses only. It still needs a live run on a machine with normal internet access.

## Next actions

1. Review the candidate's prior art and scientific value against the official Track 03 brief; recommend whether to retain it or replace it.
2. With Hari, lock the question and protocol TBDs, including the bottleneck/denominator, candidate tests, budgets, primary metric, seeds and stopping rule.
3. Migrate Arm A to `Ledger.append`; finish the single-agent launcher and get an independent review of `bench/baseline_prompt.md` before freezing the protocol.
4. Validate the full OpenML runner before writing/running an oracle sweep. Then complete the matched comparison, uncertainty/cost analysis, citation/novelty checks, and next-experiment write-up.
