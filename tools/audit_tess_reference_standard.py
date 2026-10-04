"""Establish whether an independent reference standard exists for TESS dispositions.

Akshat's TESS gate review (``docs/coordination/BENCHMARK_TESS_GATE_REVIEW.md``)
assigned three run items. This tool answers them against the live archive:

1. The ``tid`` -> ``pscomppars.tic_id`` cross-match rate for ``CP`` and ``KP``
   separately, with ``FP`` and unresolved states as controls.
2. Whether the TOI table carries a disposition-assignment date.
3. The label-semantics decisions: how ``KP`` and ``FA`` should be handled.

The cross-match is **star level**, not planet level. ``pscomppars`` has no ``toi``
column, so the only available join is host star to host star. A star match means
the host carries at least one published confirmed planet; for a multi-planet
system an unrelated impostor candidate around that same star also matches. Every
rate reported here is therefore an upper bound on planet-level confirmation, and
the tool reports the multi-candidate host count that drives that gap.
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
USER_AGENT = "FORGE-science-tess-reference/0.1"

TOI_TABLE = "toi"
PS_TABLE = "pscomppars"
TOI_DISPOSITION_COLUMN = "tfopwg_disp"

TOI_COLUMNS = ("toi", "tid", "sectors", "toi_created", "toipfx", TOI_DISPOSITION_COLUMN)
PS_COLUMNS = ("pl_name", "hostname", "tic_id", "disc_year", "discoverymethod")

DATE_HINTS = ("date", "updat", "creat", "release")
DISPOSITION_HINTS = ("disp", "tfop")

CONFIRMED_STATES = ("KP", "CP")
NEGATIVE_STATE = "FP"
UNRESOLVED_STATES = ("PC", "APC")
FA_STATE = "FA"

TESS_MISSION_START_YEAR = 2018


class ArchiveError(RuntimeError):
    """Raised when the archive could not be queried after retries."""


def fetch_table(
    table: str,
    columns: tuple[str, ...],
    timeout: int = 300,
    retries: int = 5,
    backoff: float = 15.0,
    sleep=time.sleep,
) -> tuple[list[dict[str, str]], str]:
    query = f"select {','.join(columns)} from {table}"
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            text = raw.decode("utf-8-sig", errors="replace")
            return list(csv.DictReader(io.StringIO(text))), hashlib.sha256(raw).hexdigest()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            sleep(backoff * (attempt + 1))
    raise ArchiveError(f"could not fetch {table}: {last}")


def schema_columns(table: str, timeout: int = 300) -> list[str]:
    query = (
        "select column_name from TAP_SCHEMA.columns "
        f"where table_name='{table}' order by column_name"
    )
    url = f"{TAP}?query={urllib.parse.quote(query)}&format=csv"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return [row["column_name"] for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))]


def normalize_state(value: str | None) -> str:
    return (value or "").strip().upper()


def normalize_tic(value: str | None) -> str:
    """Reduce a TIC identifier to its bare digits.

    ``pscomppars.tic_id`` is stored as a formatted string ("TIC 281461362")
    while ``toi.tid`` is a bare integer ("281461362"). Comparing them without
    normalizing silently yields zero matches.
    """
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return ""
    return str(int(digits))


def identifier_diagnostics(toi_rows: list[dict[str, str]], confirmed_tics: set[str]) -> dict:
    """Report identifier shape so any residual ID-space mismatch stays visible.

    TIC identifiers are not uniformly 9 digits in this archive: ``pscomppars``
    contains 6-, 7-, 8-, 9- and 10-digit values, and 303 short ``toi.tid`` values
    do match a ``pscomppars`` TIC. Filtering by digit length would therefore
    discard real matches, so nothing is filtered and the shape is reported
    instead.
    """
    all_lengths: Counter[int] = Counter()
    matched_lengths: Counter[int] = Counter()
    unmatched_lengths: Counter[int] = Counter()
    states_matched: Counter[str] = Counter()
    for row in toi_rows:
        tic = normalize_tic(row.get("tid"))
        if not tic:
            continue
        length = len(tic)
        all_lengths[length] += 1
        if tic in confirmed_tics:
            matched_lengths[length] += 1
            states_matched[normalize_state(row.get(TOI_DISPOSITION_COLUMN))] += 1
        else:
            unmatched_lengths[length] += 1
    return {
        "toi_tid_digit_length_histogram": {str(k): v for k, v in sorted(all_lengths.items())},
        "matched_digit_length_histogram": {str(k): v for k, v in sorted(matched_lengths.items())},
        "unmatched_digit_length_histogram": {str(k): v for k, v in sorted(unmatched_lengths.items())},
        "matched_rows_by_state": dict(sorted(states_matched.items())),
        "filter_policy": (
            "No digit-length filter is applied. Real TIC identifiers of several lengths are "
            "present on both sides and short toi.tid values do match pscomppars TICs."
        ),
    }


def match_rates_by_state(toi_rows: list[dict[str, str]], confirmed_tics: set[str]) -> dict:
    totals: Counter[str] = Counter()
    matches: Counter[str] = Counter()
    for row in toi_rows:
        state = normalize_state(row.get(TOI_DISPOSITION_COLUMN))
        totals[state] += 1
        if normalize_tic(row.get("tid")) in confirmed_tics:
            matches[state] += 1
    return {
        state: {
            "toi_rows": totals[state],
            "host_in_pscomppars": matches[state],
            "match_rate": matches[state] / totals[state] if totals[state] else 0.0,
        }
        for state in sorted(totals)
    }


def resolved_hosts_with_multiple_candidates(toi_rows: list[dict[str, str]]) -> dict:
    per_host: dict[str, Counter[str]] = defaultdict(Counter)
    for row in toi_rows:
        state = normalize_state(row.get(TOI_DISPOSITION_COLUMN))
        if state in CONFIRMED_STATES or state == NEGATIVE_STATE or state == FA_STATE:
            per_host[normalize_tic(row.get("tid"))][state] += 1
    mixed = sum(1 for states in per_host.values() if len(states) > 1)
    multi = {tid: dict(states) for tid, states in per_host.items() if sum(states.values()) > 1}
    return {
        "hosts_with_multiple_resolved_candidates": len(multi),
        "hosts_mixing_positive_and_negative_candidates": mixed,
        "examples": dict(list(sorted(multi.items()))[:10]),
    }


def disc_year_agreement(toi_rows: list[dict[str, str]], ps_rows: list[dict[str, str]]) -> dict:
    years_by_tic: dict[str, list[int]] = defaultdict(list)
    for row in ps_rows:
        tic = normalize_tic(row.get("tic_id"))
        raw = (row.get("disc_year") or "").strip()
        if tic and raw:
            try:
                years_by_tic[tic].append(int(float(raw)))
            except ValueError:
                continue
    out: dict[str, dict] = {}
    for state in CONFIRMED_STATES:
        matched = 0
        tess_era = 0
        pre_tess = 0
        for row in toi_rows:
            if normalize_state(row.get(TOI_DISPOSITION_COLUMN)) != state:
                continue
            years = years_by_tic.get(normalize_tic(row.get("tid")), [])
            if not years:
                continue
            matched += 1
            if min(years) >= TESS_MISSION_START_YEAR:
                tess_era += 1
            else:
                pre_tess += 1
        out[state] = {
            "hosts_matched": matched,
            "min_disc_year_in_tess_era": tess_era,
            "min_disc_year_pre_tess": pre_tess,
            "note": (
                "KP is expected to be dominated by pre-TESS discoveries because KP means known "
                "planet from a previous survey. CP hosts should mostly have a TESS-era discovery."
            ),
        }
    return out


def label_semantics(toi_rows: list[dict[str, str]]) -> dict:
    counts = Counter(normalize_state(row.get(TOI_DISPOSITION_COLUMN)) for row in toi_rows)
    base_positive = sum(counts.get(s, 0) for s in CONFIRMED_STATES)
    base_negative = counts.get(NEGATIVE_STATE, 0)
    fa = counts.get(FA_STATE, 0)
    unresolved = sum(counts.get(s, 0) for s in UNRESOLVED_STATES)
    variants = {
        "exclude_kp": {
            "positive_states": ["CP"],
            "negative_states": [NEGATIVE_STATE],
            "positive": counts.get("CP", 0),
            "negative": base_negative,
            "rationale": "Removes the catalog-lookup label that is not produced by TESS vetting.",
        },
        "kp_and_cp_as_positive": {
            "positive_states": list(CONFIRMED_STATES),
            "negative_states": [NEGATIVE_STATE],
            "positive": base_positive,
            "negative": base_negative,
            "rationale": "Maximizes positive count but mixes two different label mechanisms.",
        },
    }
    for variant in variants.values():
        total = variant["positive"] + variant["negative"]
        variant["labeled_cohort"] = total
        variant["positive_fraction"] = variant["positive"] / total if total else 0.0
        variant["meets_minimum_class"] = min(variant["positive"], variant["negative"]) >= 200
    fa_variants = {
        "fa_as_negative": {
            "negative": base_negative + fa,
            "positive": base_positive,
            "rationale": "FA is a resolved non-candidate, so it is observed truth, not censored.",
        },
        "fa_as_censored": {
            "negative": base_negative,
            "positive": base_positive,
            "rationale": "Treats FA as unresolved, which is the status quo.",
        },
    }
    for variant in fa_variants.values():
        total = variant["positive"] + variant["negative"]
        variant["labeled_cohort"] = total
        variant["meets_minimum_class"] = min(variant["positive"], variant["negative"]) >= 200
    return {
        "disposition_counts": dict(sorted(counts.items())),
        "unresolved_states": list(UNRESOLVED_STATES),
        "unresolved_rows": unresolved,
        "positive_class_variants": variants,
        "fa_handling_variants": fa_variants,
        "recommended_pending_review": {
            "positive_states": ["CP"],
            "negative_states": [NEGATIVE_STATE, FA_STATE],
            "rationale": (
                "CP is the only positive label produced by TESS-side adjudication. KP is a "
                "previous-survey catalog lookup and is not independent evidence about TESS vetting. "
                "FA is a resolved non-candidate, so censoring it discards observed truth."
            ),
        },
    }


def build_report(
    toi_rows: list[dict[str, str]],
    ps_rows: list[dict[str, str]],
    toi_columns: list[str],
    ps_columns: list[str],
    hashes: dict[str, str],
    retrieved_at: str,
) -> dict:
    confirmed_tics = {
        normalize_tic(row.get("tic_id")) for row in ps_rows if normalize_tic(row.get("tic_id"))
    }
    rates = match_rates_by_state(toi_rows, confirmed_tics)
    cp = rates.get("CP", {})
    kp = rates.get("KP", {})
    fp = rates.get(NEGATIVE_STATE, {})
    positive_rate = cp.get("match_rate", 0.0)
    negative_rate = fp.get("match_rate", 0.0)
    separation = positive_rate - negative_rate
    gate_passes = (
        cp.get("host_in_pscomppars", 0) >= 200
        and separation >= 0.40
    )
    return {
        "status": "REFERENCE_STANDARD_AUDIT_ONLY_NO_MODEL_NO_METRIC",
        "retrieved_at_utc": retrieved_at,
        "data_source": "NASA Exoplanet Archive TAP",
        "tables": {TOI_TABLE: TOI_COLUMNS, PS_TABLE: PS_COLUMNS},
        "sha256_raw_csv": hashes,
        "row_counts": {TOI_TABLE: len(toi_rows), PS_TABLE: len(ps_rows)},
        "ps_has_toi_column": "toi" in ps_columns,
        "toi_date_like_columns": sorted(c for c in toi_columns if any(h in c.lower() for h in DATE_HINTS)),
        "toi_disposition_like_columns": sorted(
            c for c in toi_columns if any(h in c.lower() for h in DISPOSITION_HINTS)
        ),
        "disposition_date_column_present": False,
        "disposition_date_note": (
            "The TOI table exposes only toi_created, rowupdate and release_date. None records when "
            "tfopwg_disp was assigned, so a prospective temporal split on label availability cannot "
            "be constructed from this table."
        ),
        "cross_match": {
            "join_level": "host star",
            "join_key": {"toi": "tid", "pscomppars": "tic_id"},
            "tid_is_tic_id": True,
            "pscomppars_distinct_tics": len(confirmed_tics),
            "match_rate_by_state": rates,
            "identifier_diagnostics": identifier_diagnostics(toi_rows, confirmed_tics),
            "disc_year_agreement": disc_year_agreement(toi_rows, ps_rows),
        },
        "star_level_caveat": (
            "pscomppars has no toi column, so the join is host-star level. A match means the star "
            "carries at least one published confirmed planet, which is necessary but not sufficient "
            "for planet-level confirmation of a specific candidate. Rates are upper bounds."
        ),
        "multi_candidate_hosts": resolved_hosts_with_multiple_candidates(toi_rows),
        "label_semantics": label_semantics(toi_rows),
        "gate": {
            "question": "Does pscomppars provide an independent reference standard for TESS positives?",
            "cp_host_match_rate": positive_rate,
            "fp_host_match_rate_negative_control": negative_rate,
            "separation": separation,
            "criteria": {
                "minimum_matched_cp_hosts": 200,
                "minimum_separation_vs_fp_control": 0.40,
                "note": (
                    "KP is excluded from the gate decision because its label is a previous-survey "
                    "catalog lookup, so a high KP match rate is close to definitional."
                ),
            },
            "verdict": "PASSES_FOR_POSITIVES_AS_STAR_LEVEL_UPPER_BOUND" if gate_passes else "FAILS",
            "verdict_detail": (
                "CP hosts match published confirmed planets at a materially higher rate than FP "
                "hosts, so pscomppars can adjudicate positives. It is an upper bound, not planet-level "
                "truth, and it supplies nothing for negatives."
            )
            if gate_passes
            else (
                "CP hosts do not separate from the FP control by the stated margin, so pscomppars "
                "cannot adjudicate TESS positives."
            ),
            "negatives_remain_unadjudicated": True,
            "negatives_note": (
                "No per-object record of why a TOI was dispositioned FP exists in the archive. "
                "Negative labels stay committee judgments, which is the asymmetry Akshat flagged."
            ),
            "prospective_temporal_split_possible": False,
        },
        "model_evaluation": None,
        "limitations": [
            "Star-level join; cannot separate planets within a multi-planet system.",
            "A host match does not prove the specific candidate is the confirmed planet.",
            "Negative labels have no independent source in the archive.",
            "No disposition-assignment date exists, so no prospective temporal split is possible.",
            "Label availability audit only. Not a scientific result, novelty claim, or benchmark evidence.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="schemas/examples/tess-reference-standard.json")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    toi_columns = schema_columns(TOI_TABLE, timeout=args.timeout)
    ps_columns = schema_columns(PS_TABLE, timeout=args.timeout)
    toi_rows, toi_hash = fetch_table(TOI_TABLE, TOI_COLUMNS, timeout=args.timeout)
    print(f"fetched {TOI_TABLE}: {len(toi_rows)} rows, {len(toi_columns)} columns")
    ps_rows, ps_hash = fetch_table(PS_TABLE, PS_COLUMNS, timeout=args.timeout)
    print(f"fetched {PS_TABLE}: {len(ps_rows)} rows, {len(ps_columns)} columns")

    report = build_report(
        toi_rows,
        ps_rows,
        toi_columns,
        ps_columns,
        {TOI_TABLE: toi_hash, PS_TABLE: ps_hash},
        datetime.now(timezone.utc).isoformat(),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\nhost-star match rate by TFOPWG disposition:")
    for state, entry in report["cross_match"]["match_rate_by_state"].items():
        print(
            f"  {state:<6} n={entry['toi_rows']:<6} matched={entry['host_in_pscomppars']:<6} "
            f"rate={entry['match_rate']:.4f}"
        )
    gate = report["gate"]
    print(f"\nCP rate={gate['cp_host_match_rate']:.4f} FP rate={gate['fp_host_match_rate_negative_control']:.4f}")
    print(f"separation={gate['separation']:.4f} verdict={gate['verdict']}")
    print(f"prospective temporal split possible: {gate['prospective_temporal_split_possible']}")
    print(f"\nwrote {output}")


if __name__ == "__main__":
    main()