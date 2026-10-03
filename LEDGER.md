# FORGE event ledger

Append-only, hash-chained event log in SQLite. Every agent writes here; the UI and CLI read from here.

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m pytest
```

## Usage

```python
from core.ledger import Ledger, ValidationError

ledger = Ledger()                      # results/ledger.db (or $FORGE_LEDGER_DB, or Ledger("some/path.db"))
event = ledger.append(
    run_id="demo", agent="hypothesizer", type="HYPOTHESIS_PROPOSED",
    payload={"hid": "H1", "claim": "...", "prediction": "...", "falsifier": "...", "prior": 0.6},
    refs={"hid": "H1"}, ai_generated=True,
)                                      # returns the stored event; raises ValidationError and writes nothing if invalid

ledger.read("demo", after_seq=0)       # list of events, ordered by seq
ledger.runs()                          # ["demo", ...]
ledger.verify("demo")                  # (True, None) or (False, first_bad_seq)
ledger.export_jsonl("demo", "demo.jsonl")
Ledger("other.db").import_jsonl("demo.jsonl")   # keeps seq/ts/hashes; refuses a run_id that already exists
ledger.import_jsonl("events.jsonl", validate_payloads=False)   # envelope + chain only, e.g. for bench/arm_a.py episodes

for event in ledger.subscribe("demo", after_seq=0):   # blocks, polls every 0.2s; feed this to SSE
    ...
```

`subscribe` runs forever by default. Pass `idle_timeout=5` to stop after 5s without a new event.

Appends are safe from multiple threads and processes: `seq` and `prev_hash` are computed inside a
`BEGIN IMMEDIATE` transaction. Create a `Ledger` wherever you need one; they all share the file.

## Envelope

The envelope is the team's shared contract, `schemas/event.schema.json`. No other top-level fields are allowed.

| field | type | set by | notes |
|---|---|---|---|
| `schema_version` | str | ledger | `"1.0"` |
| `seq` | int | ledger | starts at 1, +1 per event within a `run_id` |
| `ts` | str | ledger | ISO-8601 UTC, e.g. `2026-10-04T09:15:02.123Z` |
| `run_id` | str | caller | |
| `agent` | str | caller | any non-empty string; usually `librarian` `hypothesizer` `referee` `planner` `experimenter` `analyst` `safety` `system` |
| `type` | str | caller | one of the event types below |
| `refs` | dict | caller | optional ids: `hid`, `eid`, `parent`, `gate_id` (free-form). Left out of the event when empty |
| `payload` | dict | caller | validated against the schema for `type` |
| `ai_generated` | bool | caller | default `False` |
| `prev_hash` | str | ledger | hash of the previous event in the run; `"GENESIS"` for the first |
| `hash` | str | ledger | `sha256(prev_hash + canonical_json(event_without_hash))`, hex |

`canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`

## Event types and payloads

Schemas are in `schemas/`. Listed fields are required; extra fields are allowed, so you can add
your own without breaking validation. `core.schemas.validate(type, payload)` checks a payload without writing.

Every run should start with `RUN_CREATED` and end with `RUN_COMPLETED`: `bench/report.py` times the run
between those two events. Keys marked "benchmark" below are the ones `bench/report.py` reads
(see `docs/coordination/BENCHMARK.md`).

### RUN_CREATED (`run_created.json`)
Only `question` is required.
```json
{"question": "On OpenML task 7592 (adult), does adding missingness indicators to median/mode imputation change logistic-regression accuracy?", "budget": 100.0, "mode": "fake"}
```

### EVIDENCE_ADDED (`evidence.json`)
`ref` is a DOI or arXiv id. `quote_span` is the verbatim quote that supports the claim
(`tools/citation_check.py` calls the same thing `quote` in its own input file).
```json
{"claims": [{"text": "Missingness indicators can help when missingness is informative.", "ref": "arXiv:0000.00001", "quote_span": "adding an indicator lets the model use informative missingness"}]}
```

### HYPOTHESIS_PROPOSED (`hypothesis.json`)
The id field is `hid` (benchmark). `prior` is in 0..1.
```json
{"hid": "H1", "claim": "Adding missingness indicators to median/mode imputation raises accuracy on adult.", "prediction": "Accuracy gain of about 0.004.", "falsifier": "Gain below 0.001 with a CI that includes 0.", "prior": 0.6}
```

### NOVELTY_VERDICT (`novelty.json`)
`label` is `NOVEL`, `KNOWN`, `CONTRADICTED` or `UNCERTAIN`.
```json
{"hid": "H3", "label": "KNOWN", "prior_art": ["arXiv:0000.00001"]}
```

### PREDICTION_COMMITTED (`prediction.json`)
A distribution, not a point value: `sd` must be > 0. `eid` is optional in the schema, but include it
(benchmark): a run only counts as preregistered if a `PREDICTION_COMMITTED` with its `eid` comes before its `RUN_STARTED`.
```json
{"hid": "H1", "eid": "E1", "metric": "accuracy_gain", "mean": 0.004, "sd": 0.001}
```

### EXPERIMENT_SELECTED (`spec.json`)
`chosen` must be the `eid` of one of the candidates.
```json
{"candidates": [{"eid": "E1", "hid": "H1", "design": "Median/mode imputation with vs without missingness indicators, 10-fold CV", "est_cost": 12.0, "eig": 0.41}, {"eid": "E2", "hid": "H2", "design": "Same comparison, scored on rows with and without missing values", "est_cost": 30.0, "eig": 0.52}], "chosen": "E1", "budget_left": 88.0}
```

### RUN_STARTED (`run.json`)
`eid` and `hid` are required (benchmark). `candidate` is optional: the name or configuration being tested (string or object).
```json
{"eid": "E1", "hid": "H1", "code_hash": "9f2c1e7", "data_ver": "openml-task-7592/adult-v2", "seed": 0, "candidate": {"imputation": "median_mode", "missing_indicators": true}}
```

### RUN_FINISHED (`run.json`)
Same as RUN_STARTED plus two required fields (benchmark): `status` (`"ok"` or a failure value) and
`metrics` (object of numbers; `{}` is fine for a failed run).
```json
{"eid": "E1", "hid": "H1", "code_hash": "9f2c1e7", "data_ver": "openml-task-7592/adult-v2", "seed": 0, "status": "ok", "metrics": {"accuracy": 0.8516, "accuracy_baseline": 0.8514, "accuracy_gain": 0.0002}}
```

### FINDING (`finding.json`)
`ci` is `[low, high]`. `verdict` is `SUPPORTS`, `REFUTES` or `INCONCLUSIVE`.
```json
{"eid": "E1", "effect": 0.0002, "ci": [-0.0011, 0.0015], "verdict": "INCONCLUSIVE"}
```

### CONSENSUS (`consensus.json`)
`agreement` is in 0..1.
```json
{"eid": "E1", "agreement": 0.83, "accepted": true}
```

### SURPRISE (`surprise.json`)
```json
{"eid": "E1", "hid": "H1", "observed": 0.0002, "surprise_score": 3.8, "threshold": 2.0}
```

### REPLAN (`replan.json`)
`reopened` holds hypothesis or experiment ids. `trigger_eid` is optional in the schema, but include it
(benchmark): only replans that name the triggering experiment are counted.
```json
{"reason": "E1 gain is far below the committed prediction for H1.", "trigger_eid": "E1", "reopened": ["H4"]}
```

### POLICY_DENIED (`policy.json`)
`policy_id` is `P1`..`P6`.
```json
{"policy_id": "P1", "target_agent": "librarian", "reason": "Bad citation: arXiv:0000.99999 does not resolve."}
```

### GATE_OPENED (`gate.json`)
`status` is `pending`, `approved` or `denied`. `risk` is a free-form string.
```json
{"gate_id": "G1", "action": "Publish the E3 finding to the shared report", "risk": "medium", "status": "pending"}
```

### GATE_RESOLVED (`gate.json`)
```json
{"gate_id": "G1", "action": "Publish the E3 finding to the shared report", "risk": "medium", "status": "approved"}
```

### RUN_COMPLETED (`run_completed.json`)
Only `status` is required (free-form, e.g. `completed`, `budget_exhausted`, `aborted`).
```json
{"status": "completed", "summary": "2 experiments, 1 replan, 1 gate."}
```

### ERROR (`error.json`)
Only `message` is required.
```json
{"message": "sandbox timeout after 300s", "where": "experimenter"}
```

## Fake run generator

Writes 31 schema-valid events covering every type except `ERROR` (all data is made up), through the real
`Ledger.append`. It is shaped like the science lane's provisional candidate (OpenML task 7592, adult, accuracy);
every number and citation in it is invented. A copy of its output is checked in as `schemas/examples/sample-run.jsonl`, with real hashes,
so it can be replayed with `import_jsonl`.

```bash
.venv/bin/python -m core.fake_events --run-id demo --delay 0.5
```

`--delay` is seconds between events; `--db path` picks another ledger file. Running it twice with
the same `--run-id` appends a second copy to the same run.

## Verify a run

```bash
.venv/bin/python -m cli.verify demo
```

Prints `run 'demo': chain OK, 31 events` and exits 0, or `CHAIN BROKEN at seq N` and exits 1.
