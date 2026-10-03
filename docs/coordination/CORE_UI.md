# Core + UI + CLI lane: status and interfaces

- **Owner:** Ish
- **Branch:** `work/core-ui`
- **Status:** ledger, payload schemas, fake event generator and `verify` CLI are built and tested locally (24 tests pass on Python 3.9.6). Code is not pushed yet. Server (SSE), full CLI and UI are not started.

## Done (local, to be pushed in a follow-up PR)

- `core/ledger.py`: append-only, hash-chained SQLite ledger with `append`, `read`, `runs`, `verify`, `subscribe`, `export_jsonl`, `import_jsonl`.
- `core/schemas.py` + `schemas/*.json`: one payload schema per event type; the envelope is `schemas/event.schema.json`.
- `core/fake_events.py`: writes a 31-event fixture run covering every event type except `ERROR`. It is shaped like Hari's provisional candidate (OpenML task 7592, adult, accuracy; see `SCIENCE_CONTRACT.md`), and every run reports an `accuracy` metric. All numbers and citations in it are made up; it will be updated if the task or metric changes.
- `cli/verify.py`: checks a run's hash chain; non-zero exit on failure.
- Full reference with one example per payload: `LEDGER.md`.

## Proposed change to the shared event schema (needs agreement)

Add one optional top-level field to `schemas/event.schema.json`:

```json
"refs": {"type": "object"}
```

It holds cross-reference ids (`hid`, `eid`, `parent`, `gate_id`) so the UI can link events without parsing payloads. The original technical design has it; the bootstrap schema does not, and forbids extra fields. The change is additive. If anyone objects, the fallback is to keep these ids in the payload only.

Nothing else in the envelope changes. The first event's `prev_hash` is 64 zeros, which the schema already allows.

## Payload keys (reply to Akshat's proposal in `BENCHMARK.md`)

Confirmed and implemented as proposed:

| Event | Keys | Enforced by the ledger? |
|---|---|---|
| `HYPOTHESIS_PROPOSED` | `hid` | required |
| `RUN_STARTED` | `eid`, `hid`, `candidate` (optional) | `eid`, `hid` required |
| `RUN_FINISHED` | `eid`, `status`, `metrics` | all required |
| `GATE_OPENED` / `GATE_RESOLVED` | `gate_id` | required |
| `PREDICTION_COMMITTED` | `eid` | optional (see below) |
| `REPLAN` | `trigger_eid` | optional (see below) |

`bench/report.py` was run on the fixture: it times the run from `RUN_CREATED` to `RUN_COMPLETED` and reports 4 hypotheses, 2 attempts, 1 replan and 0 preregistration violations. With `metric_name: accuracy` in the episode manifest it also reports 2 valid experiments and 2 hypotheses tested.

## Not blocking anyone

The ledger and UI are built against the fake generator and do not depend on the science question. No lane needs to wait for this one; the reverse is also true.

## Decisions needed

- **All:** accept `refs` in the shared schema, or not.
- **Hari (science):** are predictions committed per hypothesis or per experiment? If per experiment, `eid` on `PREDICTION_COMMITTED` becomes required. Today an event without it is accepted and the benchmark silently counts the run as not preregistered.
- **Akshat:** should `trigger_eid` on `REPLAN` be required? Replans without it are not counted.
- **Akshat:** evidence claims use `quote_span`; `tools/citation_check.py` reads `quote`. One side renames, or the caller maps the key.
- **Saksham (orchestration):** agent names are free-form strings in the envelope; send the names the Omnigent agents and the baseline arm will log under.

## Next actions

1. Push the ledger code to `work/core-ui` and open a PR (Ish).
2. `server.py` with an SSE endpoint on top of `Ledger.subscribe`.
3. UI and `forge tail` against the fake run.
