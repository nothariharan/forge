"""Uncertainty helpers for the benchmark report (standard library only).

See bench/PROTOCOL.md section 9 for which interval is used where.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Callable, Optional, Sequence

Interval = tuple[Optional[float], Optional[float]]

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> Interval:
    """Wilson score interval for a binomial proportion k/n."""
    if n <= 0:
        return (None, None)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lower = 0.0 if k == 0 else max(0.0, centre - half)
    upper = 1.0 if k == n else min(1.0, centre + half)
    return (lower, upper)


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    total = 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    for i in range(k + 1):
        log_term = math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q
        total += math.exp(log_term)
    return min(1.0, total)


def _bisect(f: Callable[[float], float], target: float, lo: float = 0.0, hi: float = 1.0, iters: int = 100) -> float:
    """Find p in [lo, hi] with f(p) == target, for f decreasing in p."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> Interval:
    """Exact (Clopper-Pearson) interval for a binomial proportion k/n."""
    if n <= 0:
        return (None, None)
    # Lower bound solves P(X >= k | p) = alpha/2; cdf(k-1) is decreasing in p.
    lower = 0.0 if k == 0 else _bisect(lambda p: _binom_cdf(k - 1, n, p), 1 - alpha / 2)
    # Upper bound solves P(X <= k | p) = alpha/2.
    upper = 1.0 if k == n else _bisect(lambda p: _binom_cdf(k, n, p), alpha / 2)
    return (lower, upper)


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 1], of an already sorted list."""
    if not sorted_values:
        raise ValueError("empty sequence")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def paired_bootstrap(
    pairs: Sequence[tuple[float, float]],
    stat: Callable[[Sequence[float]], float] = statistics.median,
    kind: str = "diff",
    n_resamples: int = 10_000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """Paired bootstrap over seeds for B vs A.

    pairs: (a, b) per seed. kind="diff" uses b - a, kind="ratio" uses b / a
    (seeds with a == 0 are dropped and counted). Returns the point estimate,
    a percentile interval, and how many pairs were used.
    """
    if kind == "diff":
        values = [b - a for a, b in pairs]
        dropped = 0
    elif kind == "ratio":
        values = [b / a for a, b in pairs if a != 0]
        dropped = len(pairs) - len(values)
    else:
        raise ValueError("kind must be 'diff' or 'ratio'")
    if not values:
        return {"estimate": None, "ci": (None, None), "n_pairs": 0, "dropped": dropped, "distinct_resamples": 0}

    rng = random.Random(seed)
    n = len(values)
    boot = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples))
    return {
        "estimate": stat(values),
        "ci": (percentile(boot, alpha / 2), percentile(boot, 1 - alpha / 2)),
        "n_pairs": n,
        "dropped": dropped,
        # With n pairs there are only C(2n-1, n) distinct resamples; tiny n gives coarse intervals.
        "distinct_resamples": math.comb(2 * n - 1, n),
    }
