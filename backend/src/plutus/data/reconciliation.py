from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_CLOSE_DIFF_WARN_PCT = 1.0
_SPLIT_RATIO_DISAGREEMENT = 0.30  # 30% gap in day-over-day ratio implies a split mismatch


@dataclass(frozen=True)
class ReconciliationReport:
    symbol: str
    primary_source: str
    fallback_source: str
    max_close_diff_pct: float
    max_volume_diff_pct: float
    split_disagreement: bool
    warnings: list[str] = field(default_factory=list)


def _max_pct_diff(a: pd.Series, b: pd.Series) -> float:
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return 0.0
    av = a.loc[common].astype(float)
    bv = b.loc[common].astype(float)
    denom = av.abs().replace(0.0, np.nan)
    pct = ((av - bv).abs() / denom * 100.0).dropna()
    return float(pct.max()) if not pct.empty else 0.0


def _has_split_disagreement(primary: pd.DataFrame, fallback: pd.DataFrame) -> bool:
    common = primary.index.intersection(fallback.index)
    if len(common) < 2:
        return False
    p = primary.loc[common, "close"].astype(float)
    f = fallback.loc[common, "close"].astype(float)
    p_ratio = (p / p.shift(1)).dropna()
    f_ratio = (f / f.shift(1)).dropna()
    idx = p_ratio.index.intersection(f_ratio.index)
    if len(idx) == 0:
        return False
    ratio_gap = (p_ratio.loc[idx] - f_ratio.loc[idx]).abs()
    return bool((ratio_gap > _SPLIT_RATIO_DISAGREEMENT).any())


def reconcile(
    primary: pd.DataFrame,
    fallback: pd.DataFrame,
    primary_source: str,
    fallback_source: str,
    symbol: str = "",
    window_days: int = 30,
) -> ReconciliationReport:
    primary_w = primary.tail(window_days)
    fallback_w = fallback.tail(window_days)

    max_close = _max_pct_diff(primary_w["close"], fallback_w["close"])
    max_vol = (
        _max_pct_diff(primary_w["volume"], fallback_w["volume"])
        if "volume" in primary_w and "volume" in fallback_w
        else 0.0
    )
    split = _has_split_disagreement(primary_w, fallback_w)

    warnings: list[str] = []
    if max_close > _CLOSE_DIFF_WARN_PCT:
        msg = f"close diff {max_close:.2f}% exceeds {_CLOSE_DIFF_WARN_PCT}% between {primary_source}/{fallback_source}"
        warnings.append(msg)
        logger.warning(msg, extra={"symbol": symbol})
    if split:
        msg = f"split disagreement between {primary_source}/{fallback_source}"
        warnings.append(msg)
        logger.critical(msg, extra={"symbol": symbol})

    return ReconciliationReport(
        symbol=symbol,
        primary_source=primary_source,
        fallback_source=fallback_source,
        max_close_diff_pct=max_close,
        max_volume_diff_pct=max_vol,
        split_disagreement=split,
        warnings=warnings,
    )
