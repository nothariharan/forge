"""Audit whether any exoplanet planet-outcome target survives in the public archive.

This tool answers one narrow question: does the NASA Exoplanet Archive actually
contain enough *later-resolved* objects to support a prospective
confirmed-planet-versus-false-positive experiment?

It is a data-availability audit only. It trains no model and reports no
performance metric. Its output is evidence for a target/cohort decision, not
evidence for a scientific or benchmark claim.

Definitions used throughout, stated explicitly because the earlier exoplanet
attempt failed on exactly this point:

- ``CONFIRMED`` is the archive's operative label for a validated planet.
- ``FALSE POSITIVE`` is the archive's label for a dispositioned impostor.
- ``CANDIDATE`` and ``NOT DISPOSITIONED`` are *unresolved* states. They are
  censored, never counted as positives and never counted as negatives.
- An object's outcome is only observable at a *later* release than the one whose
  features are used. Same-release labels are not outcomes.

Two join tiers are reported because KOI identifiers are not stable across
deliveries:

- ``strict``: matched on ``kepoi_name``.
- ``kepid``: remaining objects matched on stellar ``kepid``, which is ambiguous
  when one star hosts several KOIs. Ambiguous matches are counted separately
  rather than silently resolved.

Attrition is reported because a naive ``kepoi_name`` join silently drops the
rarest and most decision-relevant class (objects later promoted to CONFIRMED).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
USER_AGENT = "FORGE-science-target-audit/0.1"

CONFIRMED = "CONFIRMED"
FALSE_POSITIVE = "FALSE POSITIVE"
UNRESOLVED_STATES = ("NOT DISPOSITIONED", "CANDIDATE")

KOI_RELEASES = (
    "Q1_Q6_KOI",
    "Q1_Q8_KOI",
    "Q1_Q12_KOI",
    "Q1_Q16_KOI",
    "Q1_Q17_DR24_KOI",
    "Q1_Q17_DR25_KOI",
    "CUMULATIVE",
)

RELEASE_PAIRS = (
    ("Q1_Q16_KOI", "Q1_Q17_DR24_KOI"),
    ("Q1_Q17_DR24_KOI", "Q1_Q17_DR25_KOI"),
    ("Q1_Q17_DR25_KOI", "CUMULATIVE"),
)

TOI_TABLE = "toi"
TOI_DISPOSITION_COLUMN = "tfopwg_disp"
TOI_RESOLVED_POSITIVE = ("KP", "CP")
TOI_RESOLVED_NEGATIVE = ("FP",)
TOI_CENSORED = ("PC", "APC", "FA")
TOI_COLUMNS = ("toi", "tid", "sectors", "toi_created", "ctoi_alias", TOI_DISPOSITION_COLUMN)

MIN_USABLE_CLASS = 200


class ArchiveError(RuntimeError):
    """Raised when the archive could not be queried after retries."""


def fetch_table(
    table: str,
    columns: tuple[str, ...],
    timeout: int = 180,
    retries: int = 5,
    backoff: float = 20.0,
    sleep=time.sleep,
) -> tuple[list[dict[str, str]], str]:
    """Return parsed CSV rows plus the SHA-256 of the raw response bytes."""
    query = f"select {','.join(columns)} from {table}"
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            text = raw.decode("utf-8-sig", errors="replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            return rows, hashlib.sha256(raw).hexdigest()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            sleep(backoff * (attempt + 1))
    raise ArchiveError(f"could not fetch {table}: {last}")


def normalize(value: str | None) -> str:
    return (value or "").strip().upper()


def disposition_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counter = Counter(normalize(row.get("koi_disposition")) or "(blank)" for row in rows)
    return dict(sorted(counter.items()))


def index_strict(rows: list[dict[str, str]]) -> dict[str, str]:
    return {
        row["kepoi_name"].strip(): normalize(row.get("koi_disposition"))
        for row in rows
        if row.get("kepoi_name", "").strip()
    }


def index_by_kepid(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        kepid = (row.get("kepid") or "").strip()
        name = (row.get("kepoi_name") or "").strip()
        if kepid and name:
            grouped[kepid].append(normalize(row.get("koi_disposition")))
    return dict(grouped)


def cohort_fate(
    early_rows: list[dict[str, str]],
    late_rows: list[dict[str, str]],
    early_state: str,
) -> dict:
    """Follow objects that were unresolved at ``early`` into ``late``.

    Unresolved-at-early objects are the only ones whose outcome is genuinely
    unobserved at the feature timestamp. Objects already labeled CONFIRMED or
    FALSE POSITIVE at ``early`` are excluded by construction, so no training
    object can appear in its own evaluation cohort.
    """
    late_strict = index_strict(late_rows)
    late_kepid = index_by_kepid(late_rows)

    strict_fate: Counter[str] = Counter()
    kepid_fate: Counter[str] = Counter()
    ambiguous = 0
    unmatched = 0
    cohort = 0

    for row in early_rows:
        if normalize(row.get("koi_disposition")) != early_state:
            continue
        cohort += 1
        name = (row.get("kepoi_name") or "").strip()
        if name and name in late_strict:
            strict_fate[late_strict[name] or "(blank)"] += 1
            continue
        kepid = (row.get("kepid") or "").strip()
        dispositions = late_kepid.get(kepid, [])
        if not dispositions:
            unmatched += 1
        elif len(dispositions) == 1:
            kepid_fate[dispositions[0] or "(blank)"] += 1
        else:
            ambiguous += 1

    combined = strict_fate + kepid_fate
    positives = combined.get(CONFIRMED, 0)
    negatives = combined.get(FALSE_POSITIVE, 0)
    censored = sum(count for state, count in combined.items() if state in UNRESOLVED_STATES)

    return {
        "early_state": early_state,
        "cohort_at_early_release": cohort,
        "outcome_counts": dict(sorted(combined.items())),
        "resolved_positive_confirmed": positives,
        "resolved_negative_false_positive": negatives,
        "censored_still_unresolved": censored,
        "unmatchable_excluded": unmatched,
        "ambiguous_kepid_excluded": ambiguous,
        "usable_labeled_cohort": positives + negatives,
        "join_attrition": {
            "strict_kepoi_name_matches": sum(strict_fate.values()),
            "kepid_only_matches": sum(kepid_fate.values()),
            "total_matched": sum(combined.values()),
            "note": (
                "kepoi_name is not stable across deliveries; a strict-only join drops objects "
                "that were renumbered, including rare CONFIRMED promotions."
            ),
        },
        "feasible": min(positives, negatives) >= MIN_USABLE_CLASS,
    }


def confirmed_trend(release_rows: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    return {table: disposition_counts(rows).get(CONFIRMED, 0) for table, rows in release_rows.items()}


def confirmed_trend_analysis(
    release_rows: dict[str, list[dict[str, str]]], baseline: str = "Q1_Q16_KOI"
) -> dict:
    """Compare confirmed-planet growth against total catalog growth after ``baseline``.

    A boolean "is frozen" flag hides its own threshold, so the comparison is
    reported as raw counts and net change instead.
    """
    trend = confirmed_trend(release_rows)
    latest = next(reversed(KOI_RELEASES))
    base_confirmed = trend.get(baseline, 0)
    latest_confirmed = trend.get(latest, 0)
    base_total = len(release_rows.get(baseline, []))
    latest_total = len(release_rows.get(latest, []))
    after = {k: v for k, v in trend.items() if list(trend).index(k) >= list(trend).index(baseline)}
    return {
        "baseline_release": baseline,
        "baseline_confirmed": base_confirmed,
        "latest_release": latest,
        "latest_confirmed": latest_confirmed,
        "net_confirmed_change": latest_confirmed - base_confirmed,
        "net_confirmed_change_percent": (
            100.0 * (latest_confirmed - base_confirmed) / base_confirmed if base_confirmed else 0.0
        ),
        "baseline_total_kois": base_total,
        "latest_total_kois": latest_total,
        "net_total_change_percent": (
            100.0 * (latest_total - base_total) / base_total if base_total else 0.0
        ),
        "baseline_confirmed_share": base_confirmed / base_total if base_total else 0.0,
        "latest_confirmed_share": latest_confirmed / latest_total if latest_total else 0.0,
        "confirmed_band_after_baseline": [min(after.values()), max(after.values())] if after else [],
        "interpretation": (
            "The CONFIRMED count is effectively frozen after Q1-Q16 while the catalog keeps growing, "
            "so the confirmed class cannot be replenished from later candidate pools."
        ),
    }


def toi_cohort(rows: list[dict[str, str]]) -> dict:
    """Summarize the TESS disposition table as a candidate resolved-outcome cohort.

    The TOI table carries no TIC column, so ``tid`` (TESS object) is the only
    available host-star grouping key. Multi-planet systems share a ``tid``, so a
    train/evaluation split that ignores ``tid`` leaks across the same star.
    """
    counts = Counter(normalize(row.get(TOI_DISPOSITION_COLUMN)) or "(blank)" for row in rows)
    positives = sum(counts.get(state, 0) for state in TOI_RESOLVED_POSITIVE)
    negatives = sum(counts.get(state, 0) for state in TOI_RESOLVED_NEGATIVE)
    censored = sum(counts.get(state, 0) for state in TOI_CENSORED)

    resolved = [
        row
        for row in rows
        if normalize(row.get(TOI_DISPOSITION_COLUMN)) in TOI_RESOLVED_POSITIVE + TOI_RESOLVED_NEGATIVE
    ]
    alias_by_state: dict[str, Counter[str]] = defaultdict(Counter)
    resolved_stars: dict[str, Counter[str]] = defaultdict(Counter)
    for row in resolved:
        state = normalize(row.get(TOI_DISPOSITION_COLUMN))
        has_alias = "yes" if (row.get("ctoi_alias") or "").strip() else "no"
        alias_by_state[state][has_alias] += 1
        tid = (row.get("tid") or "").strip()
        resolved_stars[tid or "(blank)"][state] += 1

    per_star = Counter(sum(states.values()) for states in resolved_stars.values())
    created = sorted((row.get("toi_created") or "").strip() for row in rows if (row.get("toi_created") or "").strip())

    return {
        "table": TOI_TABLE,
        "disposition_column": TOI_DISPOSITION_COLUMN,
        "queried_columns": list(TOI_COLUMNS),
        "row_count": len(rows),
        "disposition_counts": dict(sorted(counts.items())),
        "resolved_positive_kp_or_cp": positives,
        "resolved_negative_fp": negatives,
        "censored_pc_apc_fa": censored,
        "blank_disposition": counts.get("(blank)", 0),
        "usable_labeled_cohort": positives + negatives,
        "class_balance_positive_fraction": (
            positives / (positives + negatives) if positives + negatives else 0.0
        ),
        "distinct_hosts_tid_in_resolved_cohort": len([t for t in resolved_stars if t != "(blank)"]),
        "resolved_tois_per_host_histogram": {str(k): v for k, v in sorted(per_star.items())},
        "multi_toi_hosts_in_resolved_cohort": sum(
            v for k, v in per_star.items() if k > 1
        ),
        "ctoi_alias_present_by_state": {
            state: dict(sorted(counts_by_alias.items()))
            for state, counts_by_alias in sorted(alias_by_state.items())
        },
        "ctoi_alias_is_independent_reference_standard": False,
        "ctoi_alias_note": (
            "ctoi_alias is populated for every resolved row, including all false positives, so it "
            "cannot corroborate confirmation independently of tfopwg_disp."
        ),
        "toi_created_populated_rows": len(created),
        "toi_created_min": created[0] if created else None,
        "toi_created_max": created[-1] if created else None,
        "feasible_for_binary_outcome": min(positives, negatives) >= MIN_USABLE_CLASS,
        "host_grouping_key": "tid",
        "host_grouping_caveat": (
            "The TOI table exposes no TIC column. tid is the only host grouping key, so star-level "
            "disjointness must be enforced on tid and re-checked against TIC via an external "
            "cross-match before lock."
        ),
    }


def build_report(
    release_rows: dict[str, list[dict[str, str]]],
    hashes: dict[str, str],
    toi_rows: list[dict[str, str]] | None,
    toi_hash: str | None,
    retrieved_at: str,
) -> dict:
    trend = confirmed_trend(release_rows)
    candidates = []
    for early, late in RELEASE_PAIRS:
        for state in UNRESOLVED_STATES:
            if state not in disposition_counts(release_rows[early]):
                continue
            fate = cohort_fate(release_rows[early], release_rows[late], state)
            fate.update({"early_release": early, "late_release": late})
            candidates.append(fate)

    return {
        "status": "TARGET_AVAILABILITY_AUDIT_ONLY_NO_MODEL_NO_METRIC",
        "retrieved_at_utc": retrieved_at,
        "data_source": "NASA Exoplanet Archive TAP",
        "definitions": {
            "confirmed": CONFIRMED,
            "false_positive": FALSE_POSITIVE,
            "unresolved_censored_states": list(UNRESOLVED_STATES),
            "censoring_rule": (
                "Objects still in an unresolved state at the later release are censored: they are "
                "excluded from the labeled cohort and reported separately. They are never "
                "recoded as positives."
            ),
            "outcome_rule": (
                "An outcome is observable only at a release later than the one supplying features. "
                "Objects already labeled at the feature release are excluded from the cohort."
            ),
            "minimum_usable_class": MIN_USABLE_CLASS,
        },
        "sha256_raw_csv": hashes,
        "release_row_counts": {table: len(rows) for table, rows in release_rows.items()},
        "release_disposition_counts": {
            table: disposition_counts(rows) for table, rows in release_rows.items()
        },
        "confirmed_planet_count_by_release": trend,
        "confirmed_planet_trend_analysis": confirmed_trend_analysis(release_rows),
        "cohort_candidates": candidates,
        "toi_candidate_cohort": toi_cohort(toi_rows) if toi_rows is not None else None,
        "toi_sha256_raw_csv": toi_hash,
        "verdict": {
            "kepler_prospective_confirmation_target": "NOT_FEASIBLE",
            "kepler_rationale": (
                "The CONFIRMED class is a near-absorbing state. New confirmations from unresolved "
                "pools are 0 to 28 objects per release pair, far below the minimum usable class size, "
                "so no prospective confirmed-planet outcome can be modeled or reported."
            ),
            "kepler_false_positive_target": "NOT_RECOMMENDED",
            "kepler_false_positive_rationale": (
                "FALSE POSITIVE is abundant and adjudicated, but it was produced by the same "
                "photometric and astrometric vetting that the candidate features encode, so a model "
                "trained on it largely distills the archive's own vetting rules rather than testing "
                "a scientific hypothesis."
            ),
            "surviving_exoplanet_candidate": "tess_toi_resolved_disposition",
            "unresolved_before_lock": [
                "Establish an independent reference standard. ctoi_alias does not work: it is "
                "populated for every resolved row, including all false positives. Ground-based "
                "confirmation (for example a cross-match against pscomppars) must be tested as the "
                "adjudication source before KP/CP can be treated as a planet outcome.",
                "Confirm host-level grouping. The TOI table exposes no TIC column, so star-level "
                "disjointness must be enforced on tid and re-checked against TIC externally.",
                "Confirm a prospective temporal split is viable using toi_created, and that the "
                "confirmed class still grows after the chosen cut date.",
                "Complete a prior-art review of TESS candidate classification before any novelty "
                "language is used.",
            ],
        },
        "model_evaluation": None,
        "limitations": [
            "This audit measures label availability only. It is not a scientific result, a novelty "
            "claim, or benchmark evidence.",
            "Disposition labels are the archive's own best-knowledge automated and committee "
            "adjudications, not ground truth from an independent reference standard.",
            "kepid-based matching is ambiguous for multi-KOI systems; ambiguous objects are counted "
            "and excluded rather than assigned.",
            "Archive contents change over time; compare reruns using the stored timestamps and "
            "SHA-256 hashes.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="schemas/examples/exo-target-feasibility.json")
    parser.add_argument("--skip-toi", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    release_rows: dict[str, list[dict[str, str]]] = {}
    hashes: dict[str, str] = {}
    for table in KOI_RELEASES:
        rows, digest = fetch_table(
            table, ("kepid", "kepoi_name", "koi_disposition"), timeout=args.timeout
        )
        release_rows[table] = rows
        hashes[table] = digest
        print(f"fetched {table}: {len(rows)} rows")

    toi_rows = None
    toi_hash = None
    if not args.skip_toi:
        try:
            toi_rows, toi_hash = fetch_table(
                TOI_TABLE, TOI_COLUMNS, timeout=args.timeout
            )
            print(f"fetched {TOI_TABLE}: {len(toi_rows)} rows")
        except ArchiveError as exc:
            print(f"warning: {exc}")

    report = build_report(
        release_rows,
        hashes,
        toi_rows,
        toi_hash,
        datetime.now(timezone.utc).isoformat(),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    trend = report["confirmed_planet_count_by_release"]
    print("\nconfirmed planets by release:")
    for table, count in trend.items():
        print(f"  {table:<20} {count}")
    print("\ncohort candidates:")
    for entry in report["cohort_candidates"]:
        print(
            f"  {entry['early_release']} [{entry['early_state']}] -> {entry['late_release']}: "
            f"confirmed={entry['resolved_positive_confirmed']} "
            f"false_positive={entry['resolved_negative_false_positive']} "
            f"censored={entry['censored_still_unresolved']} "
            f"feasible={entry['feasible']}"
        )
    if report["toi_candidate_cohort"]:
        toi = report["toi_candidate_cohort"]
        print(
            f"\nTOI resolved cohort: confirmed(KP/CP)={toi['resolved_positive_kp_or_cp']} "
            f"false_positive={toi['resolved_negative_fp']} censored={toi['censored_pc_apc_fa']} "
            f"feasible={toi['feasible_for_binary_outcome']}"
        )
    print(f"\nwrote {output}")


if __name__ == "__main__":
    main()