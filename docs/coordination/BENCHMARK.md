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

### Science contract (for Hari)

The open questions are listed in `bench/PROTOCOL.md` section 13: task ID, metric and threshold, candidate space for the oracle sweep, primary metric choice, budget values, and seed handling in `tools/openml_run.py`.

### Baseline arm (for Saksham)

Arm A must run with the same model, tools and sandbox limits as FORGE, and emit the same event types it can produce, so one report script scores both arms. I'll build the arm A runner once the Omnigent smoke test shows how agents are launched.

## Blockers

- The resolver APIs (`api.openalex.org`, `export.arxiv.org`, `api.crossref.org`) are blocked by the network policy of the cloud environment this lane was developed in. The checker is tested offline with stubbed responses only. It still needs a live run on a machine with normal internet access.

## Next actions

1. Lock the protocol TBDs with Hari once the science contract is filled in.
2. Arm A runner (`bench/arms.py`) and the baseline prompt, after the Omnigent smoke test.
3. Oracle sweep script for the locked task.
4. Novelty check on the top finding, then README limits and the submission write-up.
