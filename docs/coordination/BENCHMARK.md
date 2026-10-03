# Benchmark lane: status and interfaces

- **Owner:** Akshat
- **Branch:** `work/benchmark`
- **Status:** protocol draft v0.1, citation checker, and report generator ready. Nothing has been benchmarked yet and no results exist.

## Done

- `bench/PROTOCOL.md`: arms, metrics with numerators/denominators, budget, seeds, oracle, analysis, failure handling, artifact layout. Question-dependent fields are marked TBD (science).
- `tools/citation_check.py`: resolves DOI / arXiv / OpenAlex IDs / URLs and checks quoted spans against the abstract or a supplied full text. Resolution and quote support are reported separately (protocol S3/S4). Network errors are counted separately and never as "unresolvable".
- `bench/report.py` + `bench/stats.py`: compute every metric from episode artifacts; paired bootstrap, Wilson and Clopper-Pearson intervals; standard library only.
- Tests: `python3 -m pytest -q tests/` (needs `pytest`; `citation_check.py` needs `requests` for live use).

## Interfaces this lane depends on

### Event payload keys (for Ish, core/UI; and Saksham, orchestration)

`bench/report.py` reads these keys from `payload` in `schemas/event.schema.json` events. This is a **proposal**; nothing in the shared schema has been changed. Please confirm or tell me the names you prefer:

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

### Science contract (for Hari)

The open questions are listed in `bench/PROTOCOL.md` section 13: task ID, metric and threshold, candidate space for the oracle sweep, primary metric choice, budget values, and seed handling in `tools/openml_run.py`.

### Baseline arm (for Saksham)

Arm A must run with the same model, tools and sandbox limits as FORGE. `bench/arm_a.py` already writes arm A's events in the shared schema format (hash chained per the design doc; it should switch to `core/ledger.py` once that is merged). The remaining piece is the launcher, which depends on how the smoke test starts agents.

## Blockers

- The resolver APIs (`api.openalex.org`, `export.arxiv.org`, `api.crossref.org`) are blocked by the network policy of the cloud environment this lane was developed in. The checker is tested offline with stubbed responses only. It still needs a live run on a machine with normal internet access.

## Next actions

1. Lock the protocol TBDs with Hari once the science contract is filled in, then write the sweep spec and run the oracle.
2. ~~Baseline prompt and arm A episode tools~~ drafted: `bench/baseline_prompt.md`, `bench/arm_a.py`. Still to do: the launcher that starts the single agent with the filled prompt and budget, after the Omnigent smoke test shows how agents are launched. The prompt needs a review from someone outside the benchmark lane.
3. ~~Oracle sweep script~~ done: `bench/oracle.py`.
4. Novelty check on the top finding, then README limits and the submission write-up.
