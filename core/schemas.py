"""Payload + envelope validation. Schemas live in ../schemas/*.json.

The envelope is the team's shared contract, schemas/event.schema.json."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

# event type -> schema file (without .json)
SCHEMA_FOR = {
    "RUN_CREATED": "run_created",
    "EVIDENCE_ADDED": "evidence",
    "HYPOTHESIS_PROPOSED": "hypothesis",
    "NOVELTY_VERDICT": "novelty",
    "PREDICTION_COMMITTED": "prediction",
    "EXPERIMENT_SELECTED": "spec",
    "RUN_STARTED": "run",
    "RUN_FINISHED": "run",
    "FINDING": "finding",
    "CONSENSUS": "consensus",
    "SURPRISE": "surprise",
    "REPLAN": "replan",
    "POLICY_DENIED": "policy",
    "GATE_OPENED": "gate",
    "GATE_RESOLVED": "gate",
    "RUN_COMPLETED": "run_completed",
    "ERROR": "error",
}
EVENT_TYPES = tuple(SCHEMA_FOR)


class ValidationError(ValueError):
    """Raised for any bad event. Nothing is written when this is raised."""


def _load(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIR / f"{name}.json").read_text()))


ENVELOPE = "event.schema"
_VALIDATORS = {name: _load(name) for name in {*SCHEMA_FOR.values(), ENVELOPE}}
SCHEMA_VERSION = _VALIDATORS[ENVELOPE].schema["properties"]["schema_version"]["const"]
# The usual agent names. Not enforced: the shared contract allows any non-empty string
# (the single-agent baseline arm logs under its own name).
AGENTS = ("librarian", "hypothesizer", "referee", "planner", "experimenter", "analyst", "safety", "system")


def _check(name: str, obj, label: str, skip_required: bool = False) -> None:
    errors = (e for e in _VALIDATORS[name].iter_errors(obj) if not (skip_required and e.validator == "required"))
    err = next(errors, None)
    if err:
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        raise ValidationError(f"{label}: {where}: {err.message}")


def validate(type: str, payload: dict) -> None:
    """Validate a payload for an event type. Raises ValidationError."""
    if type not in SCHEMA_FOR:
        raise ValidationError(f"unknown event type {type!r}")
    _check(SCHEMA_FOR[type], payload, type)

    # Rules JSON Schema can't express.
    if type == "EXPERIMENT_SELECTED":
        eids = [c["eid"] for c in payload["candidates"]]
        if payload["chosen"] not in eids:
            raise ValidationError(f"{type}: chosen {payload['chosen']!r} is not one of the candidates {eids}")
    if type == "RUN_FINISHED":
        for key in ("status", "metrics"):
            if key not in payload:
                raise ValidationError(f"{type}: {key} is required")
    if type == "FINDING" and payload["ci"][0] > payload["ci"][1]:
        raise ValidationError(f"{type}: ci must be [low, high]")


def validate_envelope(event: dict, complete: bool = True) -> None:
    """Validate an event against schemas/event.schema.json. Raises ValidationError.
    complete=False is for a draft that the ledger has not yet given seq/ts/prev_hash/hash."""
    _check(ENVELOPE, event, "envelope", skip_required=not complete)
