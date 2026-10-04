"""Audit Kepler KOI disposition semantics and snapshot changes.

This is a data-ingestion/semantics feasibility check only. It deliberately does
not train a classifier or report precision: CANDIDATE is not a confirmed-planet
label, and the public catalog does not reveal the truth for unresolved objects.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TABLES = {"snapshot": "q1_q17_dr25_koi", "current": "cumulative"}
COLUMNS = ("kepoi_name", "koi_disposition", "koi_pdisposition")


def fetch_table(table: str, timeout: int = 120) -> tuple[list[dict[str, str]], str]:
    query = f"select {','.join(COLUMNS)} from {table}"
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    request = urllib.request.Request(url, headers={"User-Agent": "FORGE-science-feasibility/0.2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))
    return rows, hashlib.sha256(raw).hexdigest()


def index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        key = (row.get("kepoi_name") or "").strip()
        if key:
            result[key] = {
                "disposition": (row.get("koi_disposition") or "").strip().upper(),
                "pdisposition": (row.get("koi_pdisposition") or "").strip().upper(),
            }
    return result


def counts(rows: dict[str, dict[str, str]], column: str) -> dict[str, int]:
    return dict(sorted(Counter(row[column] or "(blank)" for row in rows.values()).items()))


def audit(snapshot: dict[str, dict[str, str]], current: dict[str, dict[str, str]], column: str) -> dict:
    common = sorted(snapshot.keys() & current.keys())
    transitions = Counter((snapshot[k][column] or "(blank)", current[k][column] or "(blank)") for k in common)
    snapshot_labeled = {"CANDIDATE", "FALSE POSITIVE"}
    initial_candidates = [k for k in common if snapshot[k][column] == "CANDIDATE"]
    outcomes = Counter(current[k][column] or "(blank)" for k in initial_candidates)
    revisions = sum(snapshot[k][column] != current[k][column] for k in common)
    return {
        "column": column,
        "common_ids": len(common),
        "snapshot_labeled_candidate_or_fp_ids": sum(snapshot[k][column] in snapshot_labeled for k in common),
        "changed_disposition_count_all_common_ids": revisions,
        "transition_counts": [
            {"snapshot": old, "current": new, "count": count}
            for (old, new), count in sorted(transitions.items())
        ],
        "snapshot_candidate_ids_by_current_disposition": dict(sorted(outcomes.items())),
        "current_candidate_is_ground_truth": False,
        "interpretation": (
            "CANDIDATE is an unresolved/possible-planet status, not a confirmed-planet label. "
            "Counts by current disposition describe catalog status transitions only; they are not PPV, "
            "planet prevalence, or classifier precision."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="schemas/examples/exo-prior-shift-feasibility.json")
    args = parser.parse_args()

    snapshot_rows, snapshot_hash = fetch_table(TABLES["snapshot"])
    current_rows, current_hash = fetch_table(TABLES["current"])
    snapshot = index_rows(snapshot_rows)
    current = index_rows(current_rows)
    result = {
        "status": "FEASIBILITY_DATA_AUDIT_ONLY_NO_MODEL_OR_PRECISION_RESULT",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "NASA Exoplanet Archive TAP",
        "tables": TABLES,
        "queried_columns": list(COLUMNS),
        "sha256_raw_csv": {TABLES["snapshot"]: snapshot_hash, TABLES["current"]: current_hash},
        "row_counts": {TABLES["snapshot"]: len(snapshot_rows), TABLES["current"]: len(current_rows)},
        "disposition_counts": {
            TABLES["snapshot"]: counts(snapshot, "disposition"),
            TABLES["current"]: counts(current, "disposition"),
        },
        "audits": [audit(snapshot, current, "disposition"), audit(snapshot, current, "pdisposition")],
        "model_evaluation": None,
        "limitations": [
            "CANDIDATE is not confirmed as a planet; unresolved cases have no observed truth label.",
            "The snapshot-to-current join reuses object identifiers and is not an independent temporal test set.",
            "Disposition transitions are descriptive catalog changes and cannot establish model precision or performance transfer.",
            "This output is for schema/data feasibility only, not scientific evidence or a benchmark result.",
        ],
        "next_requirement_for_valid_model_evaluation": (
            "Define a target with independently resolved confirmed-planet/false-positive outcomes, construct disjoint "
            "train and held-out object cohorts, and exclude or explicitly censor unresolved objects."
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {output}")


if __name__ == "__main__":
    main()
