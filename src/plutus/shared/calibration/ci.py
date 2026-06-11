from __future__ import annotations

import math

import numpy as np
from scipy.special import ndtri


def wilson_interval(successes: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = float(ndtri((1 + conf) / 2))
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_R_interval(
    rs: list[float], conf: float = 0.95, B: int = 5000, seed: int = 0
) -> tuple[float, float]:
    if not rs:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(rs, dtype=float)
    means = rng.choice(arr, size=(B, len(arr)), replace=True).mean(axis=1)
    lo = float(np.percentile(means, (1 - conf) / 2 * 100))
    hi = float(np.percentile(means, (1 + conf) / 2 * 100))
    return (lo, hi)
