from __future__ import annotations


def benjamini_hochberg(p_values: list[float], q: float = 0.10) -> list[bool]:
    """BH step-up procedure. Returns a mask (input order): True where rejected."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda kv: kv[1])
    mask = [False] * m
    max_k = -1
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= rank / m * q:
            max_k = rank
    if max_k > 0:
        for rank, (orig_idx, _) in enumerate(indexed, start=1):
            if rank <= max_k:
                mask[orig_idx] = True
    return mask


def family_size(buckets: int, bundles: int, regimes: int) -> int:
    return buckets * bundles * regimes
