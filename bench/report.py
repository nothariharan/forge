"""Compute benchmark metrics from raw episode artifacts and write the report.

Every number in the report comes from files under results/bench/<bench_id>/.
Nothing is entered by hand. See bench/PROTOCOL.md for metric definitions.

Layout read by this script:

    results/bench/<bench_id>/
      oracle.json                  optional: {"best": c, "within_threshold": [c, ...]}
      <arm>/seed-<n>/
        manifest.json              {"arm", "seed", "metric_name", "budget_end_ts"?, "rerun_reason"?, ...}
        events.jsonl               ledger events (schemas/event.schema.json)
        usage.json                 {"tokens_in", "tokens_out", "usd", "compute_seconds"}
                                   or {"agents": {name: {same keys}}}
        citations.json             output of tools/citation_check.py (optional)
        answer.json                {"candidate": c} final recommended answer (optional)

Event payload keys this script relies on (proposed; to be confirmed with the
event schema owner):

    PREDICTION_COMMITTED  payload.eid
    RUN_STARTED           payload.eid, payload.hid, payload.candidate (optional)
    RUN_FINISHED          payload.eid, payload.status ("ok" | ...), payload.metrics {name: value}
                          (a run with only RUN_FINISHED still counts as an attempt; then hid and
                          candidate are read from RUN_FINISHED and the prediction must precede it)
    HYPOTHESIS_PROPOSED   payload.hid
    REPLAN                payload.trigger_eid (the result that caused the replan)
    GATE_OPENED/RESOLVED  payload.gate_id

Usage:
    python bench/report.py results/bench/<bench_id> [--baseline A --treatment B]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stats  # noqa: E402

EPISODE_METRICS = [
    # (key, label, higher_is_better)
    ("valid_experiments_per_hour", "S1 valid experiments / hour", True),
    ("hypotheses_tested_per_hour", "S2 hypotheses tested / hour", True),
    ("unresolvable_ref_rate", "S3 unresolvable reference rate", False),
    ("unsupported_quote_rate", "S4 unsupported quote rate", False),
    ("invalid_attempt_rate", "S6 invalid attempt rate", False),
    ("prereg_violations", "S7 preregistration violations", False),
    ("replans_per_valid_experiment", "S8 result-driven replans / valid experiment", True),
    ("usd", "S9 cost (USD)", False),
    ("tokens_total", "S9 tokens", False),
    ("timed_wall_seconds", "S9 timed wall time (s)", False),
    ("usd_per_valid_experiment", "S9 USD / valid experiment", False),
    ("human_seconds", "S10 human approval time (s)", False),
    ("experiments_to_top", "Experiments to reach top candidate", False),
]


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_events(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    return sorted(events, key=lambda e: e["seq"])


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or not b:
        return None
    return a / b


def episode_metrics(episode_dir: str, oracle: Optional[dict]) -> dict:
    manifest = _load_json(os.path.join(episode_dir, "manifest.json"), {})
    events = _load_events(os.path.join(episode_dir, "events.jsonl"))
    usage = _load_json(os.path.join(episode_dir, "usage.json"), {})
    citations = _load_json(os.path.join(episode_dir, "citations.json"))
    answer = _load_json(os.path.join(episode_dir, "answer.json"))
    metric_name = manifest.get("metric_name")

    # Timed window: RUN_CREATED to RUN_COMPLETED, else to the budget cutoff, else to the last event.
    start = next((e["ts"] for e in events if e["type"] == "RUN_CREATED"), None)
    end = next((e["ts"] for e in events if e["type"] == "RUN_COMPLETED"), None)
    completed = end is not None
    end = end or manifest.get("budget_end_ts") or (events[-1]["ts"] if events else None)
    wall = (_ts(end) - _ts(start)).total_seconds() if start and end else None
    hours = wall / 3600 if wall else None

    committed: set[str] = set()
    started: dict[str, dict] = {}
    prereg_ok: dict[str, bool] = {}
    finished: dict[str, dict] = {}
    hypotheses_proposed: set[str] = set()
    replans = 0
    gate_open: dict[str, datetime] = {}
    human_seconds = 0.0

    for e in events:
        p = e.get("payload", {})
        t = e["type"]
        if t == "PREDICTION_COMMITTED" and p.get("eid"):
            committed.add(p["eid"])
        elif t == "RUN_STARTED" and p.get("eid"):
            started[p["eid"]] = p
            prereg_ok.setdefault(p["eid"], p["eid"] in committed)
        elif t == "RUN_FINISHED" and p.get("eid"):
            finished[p["eid"]] = p
            # A producer that logs only RUN_FINISHED still has its run counted; the prediction must
            # then precede the result instead of the start (whichever event comes first is used).
            prereg_ok.setdefault(p["eid"], p["eid"] in committed)
            started.setdefault(p["eid"], p)
        elif t == "HYPOTHESIS_PROPOSED" and p.get("hid"):
            hypotheses_proposed.add(p["hid"])
        elif t == "REPLAN" and p.get("trigger_eid"):
            replans += 1
        elif t == "GATE_OPENED" and p.get("gate_id"):
            gate_open[p["gate_id"]] = _ts(e["ts"])
        elif t == "GATE_RESOLVED" and p.get("gate_id") in gate_open:
            human_seconds += (_ts(e["ts"]) - gate_open.pop(p["gate_id"])).total_seconds()

    attempts = list(started)
    valid = [
        eid for eid in attempts
        if prereg_ok[eid]
        and finished.get(eid, {}).get("status") == "ok"
        and metric_name is not None
        and finished[eid].get("metrics", {}).get(metric_name) is not None
    ]
    hyps_tested = {started[eid].get("hid") for eid in valid if started[eid].get("hid")}

    experiments_to_top = None
    reached_top = None
    if oracle and oracle.get("within_threshold") is not None:
        within = oracle["within_threshold"]
        reached_top = False
        for i, eid in enumerate(valid, start=1):
            if started[eid].get("candidate") in within:
                experiments_to_top, reached_top = i, True
                break

    correct = None
    if oracle:  # no answer (crash, timeout, budget) scores as incorrect, never drops out of the denominator
        within = oracle.get("within_threshold") or [oracle.get("best")]
        correct = (answer or {}).get("candidate") in within

    if "agents" in usage:
        totals = {k: sum((a.get(k) or 0) for a in usage["agents"].values())
                  for k in ("tokens_in", "tokens_out", "usd", "compute_seconds")}
    else:
        totals = {k: usage.get(k) for k in ("tokens_in", "tokens_out", "usd", "compute_seconds")}
    tokens_total = None
    if totals["tokens_in"] is not None or totals["tokens_out"] is not None:
        tokens_total = (totals["tokens_in"] or 0) + (totals["tokens_out"] or 0)

    csum = (citations or {}).get("summary", {})
    return {
        "arm": manifest.get("arm"),
        "seed": manifest.get("seed"),
        "completed": completed,
        "rerun_reason": manifest.get("rerun_reason"),
        "timed_wall_seconds": wall,
        "attempts": len(attempts),
        "valid_experiments": len(valid),
        "invalid_attempts": len(attempts) - len(valid),
        "prereg_violations": sum(not ok for ok in prereg_ok.values()),
        "hypotheses_proposed": len(hypotheses_proposed),
        "hypotheses_tested": len(hyps_tested),
        "replans": replans,
        "valid_experiments_per_hour": _div(len(valid), hours),
        "hypotheses_tested_per_hour": _div(len(hyps_tested), hours),
        "invalid_attempt_rate": _div(len(attempts) - len(valid), len(attempts)),
        "replans_per_valid_experiment": _div(replans, len(valid)),
        "references_checked": csum.get("references_checked"),
        "unresolvable_refs": csum.get("unresolvable"),
        "unresolvable_ref_rate": csum.get("unresolvable_rate"),
        "quotes_checkable": (csum.get("quote_found", 0) + csum.get("quote_not_in_available_text", 0)) if csum else None,
        "quotes_not_found": csum.get("quote_not_in_available_text"),
        "unsupported_quote_rate": csum.get("unsupported_quote_rate"),
        "tokens_total": tokens_total,
        "usd": totals["usd"],
        "compute_seconds": totals["compute_seconds"],
        "usd_per_valid_experiment": _div(totals["usd"], len(valid)),
        "human_seconds": human_seconds,
        "reached_top": reached_top,
        "experiments_to_top": experiments_to_top,
        "correct": correct,
    }


def collect(bench_dir: str) -> tuple[dict[str, list[dict]], Optional[dict]]:
    oracle = _load_json(os.path.join(bench_dir, "oracle.json"))
    arms: dict[str, list[dict]] = {}
    for arm in sorted(os.listdir(bench_dir)):
        arm_dir = os.path.join(bench_dir, arm)
        if not os.path.isdir(arm_dir):
            continue
        for ep in sorted(os.listdir(arm_dir)):
            ep_dir = os.path.join(arm_dir, ep)
            if not (os.path.isdir(ep_dir) and ep.startswith("seed-")):
                continue
            m = episode_metrics(ep_dir, oracle)
            m["arm"] = m["arm"] or arm
            if m["seed"] is None:
                m["seed"] = int(ep.split("-", 1)[1])
            with open(os.path.join(ep_dir, "metrics.json"), "w", encoding="utf-8") as f:
                json.dump(m, f, indent=2)
            arms.setdefault(m["arm"], []).append(m)
    return arms, oracle


def compare(arms: dict[str, list[dict]], baseline: str, treatment: str) -> dict:
    a_by_seed = {m["seed"]: m for m in arms.get(baseline, [])}
    b_by_seed = {m["seed"]: m for m in arms.get(treatment, [])}
    seeds = sorted(set(a_by_seed) & set(b_by_seed))
    out: dict = {"baseline": baseline, "treatment": treatment, "paired_seeds": seeds, "metrics": {}}

    for key, label, higher_better in EPISODE_METRICS:
        pairs = [(a_by_seed[s][key], b_by_seed[s][key]) for s in seeds
                 if a_by_seed[s][key] is not None and b_by_seed[s][key] is not None]
        def shown(m: dict):
            # Censored episodes (never reached the top candidate) are reported, not hidden.
            if key == "experiments_to_top" and m["reached_top"] is False:
                return "not reached"
            return m[key]

        out["metrics"][key] = {
            "label": label,
            "higher_is_better": higher_better,
            baseline: [shown(a_by_seed[s]) for s in seeds],
            treatment: [shown(b_by_seed[s]) for s in seeds],
            "diff": stats.paired_bootstrap(pairs, kind="diff") if pairs else None,
            "ratio": stats.paired_bootstrap(pairs, kind="ratio") if pairs else None,
        }

    # Pooled rates with Wilson intervals (protocol section 9).
    pooled = {}
    for arm in (baseline, treatment):
        eps = arms.get(arm, [])
        refs = sum(m["references_checked"] or 0 for m in eps)
        unres = sum(m["unresolvable_refs"] or 0 for m in eps)
        quotes = sum(m["quotes_checkable"] or 0 for m in eps)
        missing = sum(m["quotes_not_found"] or 0 for m in eps)
        attempts = sum(m["attempts"] for m in eps)
        invalid = sum(m["invalid_attempts"] for m in eps)
        graded = [m["correct"] for m in eps if m["correct"] is not None]
        reach = [m["reached_top"] for m in eps if m["reached_top"] is not None]
        pooled[arm] = {
            "episodes": len(eps),
            "completed": sum(m["completed"] for m in eps),
            "unresolvable_refs": [unres, refs, stats.wilson(unres, refs)],
            "unsupported_quotes": [missing, quotes, stats.wilson(missing, quotes)],
            "invalid_attempts": [invalid, attempts, stats.wilson(invalid, attempts)],
            "correct": [sum(graded), len(graded), stats.clopper_pearson(sum(graded), len(graded))],
            "reached_top": [sum(reach), len(reach), stats.clopper_pearson(sum(reach), len(reach))],
        }
    out["pooled"] = pooled

    # Throughput multiplier: median over seeds of S1(B) / S1(A) (protocol section 4).
    out["throughput_multiplier"] = out["metrics"]["valid_experiments_per_hour"]["ratio"]
    return out


def _fmt(x, digits=3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.{digits}g}"
    return str(x)


def _ci(c) -> str:
    return f"[{_fmt(c[0])}, {_fmt(c[1])}]" if c and c[0] is not None else "n/a"


def render_markdown(cmp: dict, oracle: Optional[dict]) -> str:
    a, b = cmp["baseline"], cmp["treatment"]
    n = len(cmp["paired_seeds"])
    lines = [f"# Benchmark report: {b} vs {a}", ""]
    if n < 3:
        lines += [f"**PRELIMINARY: only {n} paired seed(s); the protocol requires at least 3.**", ""]
    lines += [
        f"Paired seeds: {cmp['paired_seeds']} (N={n}). Intervals are 95%. Paired bootstrap over seeds "
        "(10,000 resamples) for per-seed metrics; Wilson for pooled rates; Clopper-Pearson for correctness.",
        "",
    ]
    tm = cmp["throughput_multiplier"]
    if tm and tm["estimate"] is not None:
        lines += [f"**Throughput multiplier (median S1 {b}/{a}): {_fmt(tm['estimate'])}x, CI {_ci(tm['ci'])}, "
                  f"from {tm['n_pairs']} paired seeds.**", ""]

    lines += ["## Per-seed metrics", "",
              f"| Metric | {a} per seed | {b} per seed | median diff ({b}-{a}) [CI] | median ratio ({b}/{a}) [CI] |",
              "|---|---|---|---|---|"]
    for m in cmp["metrics"].values():
        d, r = m["diff"], m["ratio"]
        lines.append(
            f"| {m['label']} | {', '.join(_fmt(v) for v in m[a])} | {', '.join(_fmt(v) for v in m[b])} | "
            f"{_fmt(d['estimate']) + ' ' + _ci(d['ci']) if d else 'n/a'} | "
            f"{_fmt(r['estimate']) + ' ' + _ci(r['ci']) if r and r['estimate'] is not None else 'n/a'} |"
        )

    lines += ["", "## Pooled counts", "",
              "| Arm | Episodes (completed) | Unresolvable refs | Unsupported quotes | Invalid attempts | Correct answers | Reached top candidate |",
              "|---|---|---|---|---|---|---|"]
    for arm, p in cmp["pooled"].items():
        cells = [f"{k}/{n_} {_ci(ci)}" if n_ else "n/a" for k, n_, ci in
                 (p["unresolvable_refs"], p["unsupported_quotes"], p["invalid_attempts"], p["correct"], p["reached_top"])]
        lines.append(f"| {arm} | {p['episodes']} ({p['completed']}) | " + " | ".join(cells) + " |")

    lines += ["", "## Notes", "",
              "- Crashed, timed-out and no-answer episodes are included in every denominator.",
              "- S3/S4 come from tools/citation_check.py; network errors are excluded from the denominator and listed per episode.",
              "- Quote checks cover the abstract or supplied full text only.",
              "- Throughput is not discovery quality; read it alongside correctness and experiments to the top candidate."]
    if not oracle:
        lines.append("- No oracle.json: correctness and experiments to the top candidate are not scored.")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compute benchmark metrics from raw episode artifacts.")
    parser.add_argument("bench_dir")
    parser.add_argument("--baseline", default="A")
    parser.add_argument("--treatment", default="B")
    args = parser.parse_args(argv)

    arms, oracle = collect(args.bench_dir)
    if not arms:
        print(f"no episodes found under {args.bench_dir}", file=sys.stderr)
        return 1
    cmp = compare(arms, args.baseline, args.treatment)
    with open(os.path.join(args.bench_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"episodes": arms, "comparison": cmp}, f, indent=2, default=list)
    md = render_markdown(cmp, oracle)
    with open(os.path.join(args.bench_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
