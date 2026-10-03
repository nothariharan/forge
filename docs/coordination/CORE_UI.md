# Core + UI + CLI lane: status and interfaces

- **Owner:** Ish
- **Branch:** `work/core-ui`
- **Status:** ledger, payload schemas, fake event generator and `verify` CLI are in this branch with tests. Server (SSE), full CLI and UI are not started.

## Done

- `core/ledger.py`: append-only, hash-chained SQLite ledger with `append`, `read`, `runs`, `verify`, `subscribe`, `export_jsonl`, `import_jsonl`.
- `core/schemas.py` + `schemas/*.json`: one payload schema per event type; the envelope is `schemas/event.schema.json`.
- `core/fake_events.py`: writes a 31-event fixture run covering every event type except `ERROR`. It is shaped like Hari's provisional candidate (OpenML task 7592, adult, accuracy; see `SCIENCE_CONTRACT.md`). All numbers and citations in it are made up; it will be updated when the task and metric are locked (Akshat has proposed ROC AUC).
- `schemas/examples/sample-run.jsonl`: the bootstrap two-line placeholder is replaced by that fixture, with real hashes, so it replays through `import_jsonl`.
- `cli/verify.py`: checks a run's hash chain; non-zero exit on failure.
- Full reference with one example per payload: `LEDGER.md`.

## Checks run (Python 3.9.6; 3.11 not tested)

- This branch alone: `python -m pytest -q` passes, 45 tests (25 ledger + the existing benchmark and citation tests).
- This branch merged locally with `work/benchmark` (PR #2) and `work/science` (PR #3): merges without conflicts, 54 tests pass.
- `bench/report.py` on the fixture: times the run from `RUN_CREATED` to `RUN_COMPLETED`; 4 hypotheses, 2 attempts, 1 replan, 0 preregistration violations; with `metric_name: accuracy` in the manifest, 2 valid experiments.
- A real `bench/arm_a.py` episode (stub runner) imports into the ledger with `import_jsonl(path, validate_payloads=False)` and its hash chain verifies.

## Changes to shared files in this branch

- `schemas/event.schema.json`: one optional top-level field added, `"refs": {"type": "object"}`, for cross-reference ids (`hid`, `eid`, `parent`, `gate_id`). The ledger leaves it out when empty, so events without refs still match the original schema. If anyone objects, the fallback is to keep these ids in the payload only.
- `schemas/examples/sample-run.jsonl`: replaced, as above.
- `.gitignore`: `.pytest_cache/` added.

The first event's `prev_hash` is `"GENESIS"`, the same as `bench/arm_a.py`.

## Payload keys read by `bench/report.py`

Implemented as Akshat proposed in `BENCHMARK.md`:

| Event | Keys | Enforced by the ledger? |
|---|---|---|
| `HYPOTHESIS_PROPOSED` | `hid` | required |
| `RUN_STARTED` | `eid`, `hid`, `candidate` (optional) | `eid`, `hid` required |
| `RUN_FINISHED` | `eid`, `status`, `metrics` | all required |
| `GATE_OPENED` / `GATE_RESOLVED` | `gate_id` | required |
| `PREDICTION_COMMITTED` | `eid` | optional |
| `REPLAN` | `trigger_eid` | optional |

## Open: `bench/arm_a.py` payloads vs the payload schemas

`arm_a.py` writes its own `events.jsonl` today, so nothing breaks. If it switches to `Ledger.append`, these payloads are rejected by the current schemas. Either the schemas loosen or arm A adds the fields; both arms should end up with the same shapes.

| Event | arm A writes | schema requires |
|---|---|---|
| `HYPOTHESIS_PROPOSED` | `hid`, `claim`, `label` | also `prediction`, `falsifier`, `prior` |
| `PREDICTION_COMMITTED` | `eid`, `hid`, `prediction` (free object), `falsifier` | `hid`, `metric`, `mean`, `sd` (Gaussian only) |
| `RUN_FINISHED` | `eid`, `status`, `metrics`, `wall_seconds`, `error` | also `hid`, `code_hash`, `data_ver`, `seed` |
| `RUN_STARTED` | no `code_hash`, `data_ver` | `code_hash`, `data_ver` |
| `REPLAN` | `trigger_eid`, `decision` | `reason`, `reopened` |
| `FINDING` (unchanged plan) | `eid`, `decision`, `plan_changed` | `effect`, `ci`, `verdict` |
| `RUN_COMPLETED` | `candidate` | `status` |

## Not blocking anyone

The ledger and UI are built against the fake generator and do not depend on the science question.

## Decisions needed

- **All:** accept `refs` in the shared schema, or not.
- **Akshat + Ish:** resolve the arm A table above. The biggest one is the prediction shape: Gaussian `mean`/`sd` only, or a free-form distribution object as arm A and `schemas/experiment.schema.json` use.
- **Hari (science):** are predictions committed per hypothesis or per experiment? If per experiment, `eid` on `PREDICTION_COMMITTED` becomes required.
- **Akshat:** evidence claims use `quote_span`; `tools/citation_check.py` reads `quote`. One side renames, or the caller maps the key.
- **Saksham (orchestration):** agent names are free-form strings in the envelope; send the names the Omnigent agents will log under.

## Next actions

1. `server.py` with an SSE endpoint on top of `Ledger.subscribe`.
2. UI and `forge tail` against the fake run.
3. Retarget the fixture once the task and metric are locked.
