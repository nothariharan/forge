# Benchmark

No benchmark results are present yet.

- **Protocol:** [`PROTOCOL.md`](PROTOCOL.md) defines the arms, metrics with denominators, budget, seeds, analysis, failure handling and artifact layout. It is a draft until the science contract is locked.
- **Report:** `python3 bench/report.py results/bench/<bench_id>` computes every metric from the episode artifacts and writes `metrics.json` per episode plus `report.md` / `report.json`. Uses the standard library only.
- **Citations:** `python3 tools/citation_check.py <refs.json | report.md> -o citations.json` (needs `requests` and internet access).
- **Tests:** `python3 -m pytest -q tests/`

## Planned arms
- A: single-agent baseline.
- B: FORGE multi-agent harness under the same task and documented budget.

## Reporting
Every number is computed from raw artifacts under `results/bench/`. Report denominators and uncertainty. Do not infer discovery quality from throughput alone.
