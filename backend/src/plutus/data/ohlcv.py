from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from plutus.config.settings import get_settings
from plutus.data.base import OHLCVProvider
from plutus.data.reconciliation import reconcile

logger = logging.getLogger(__name__)

_OVERLAP_DAYS = 30


@dataclass(frozen=True)
class OHLCVResult:
    symbol: str
    df: pd.DataFrame | None
    source: str | None
    fallback_used: bool
    reconciliation_warning: bool
    success: bool


class OHLCVChain:
    """Primary + fallback chain. One adjusted source per symbol per run (B12)."""

    def __init__(
        self,
        primary: OHLCVProvider,
        fallback: OHLCVProvider | None,
        cache_dir: Path | None = None,
        cache_ttl_hours: int | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cache_dir = cache_dir
        self._cache_ttl_hours = (
            cache_ttl_hours
            if cache_ttl_hours is not None
            else get_settings().cache_ttl_ohlcv_hours
        )

    def fetch(self, symbol: str, start: date, end: date) -> OHLCVResult:
        cached = self._read_cache(symbol, start, end)
        if cached is not None:
            return cached

        try:
            primary_df = self._primary.fetch(symbol, start, end)
        except Exception as exc:  # provider boundary — recover via fallback
            logger.info(
                "primary provider failed; trying fallback",
                extra={
                    "symbol": symbol,
                    "provider": self._primary.name,
                    "error": str(exc),
                },
            )
            return self._fallback_only(symbol, start, end)

        reconciliation_warning = self._reconcile_overlap(symbol, primary_df, start, end)
        result = OHLCVResult(
            symbol=symbol,
            df=primary_df,
            source=self._primary.name,
            fallback_used=False,
            reconciliation_warning=reconciliation_warning,
            success=True,
        )
        self._write_cache(symbol, start, end, result)
        return result

    def _fallback_only(self, symbol: str, start: date, end: date) -> OHLCVResult:
        if self._fallback is None:
            return OHLCVResult(symbol, None, None, False, False, False)
        try:
            fb_df = self._fallback.fetch(symbol, start, end)
        except Exception as exc:
            logger.error(
                "both providers failed; dropping symbol",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return OHLCVResult(symbol, None, None, False, False, False)
        logger.info(
            "fallback used", extra={"symbol": symbol, "provider": self._fallback.name}
        )
        result = OHLCVResult(
            symbol=symbol,
            df=fb_df,
            source=self._fallback.name,
            fallback_used=True,
            reconciliation_warning=False,
            success=True,
        )
        self._write_cache(symbol, start, end, result)
        return result

    def _reconcile_overlap(
        self, symbol: str, primary_df: pd.DataFrame, start: date, end: date
    ) -> bool:
        if self._fallback is None:
            return False
        if "date" in primary_df.columns:
            overlap_start = primary_df["date"].iloc[0].date() if not primary_df.empty else start
        elif not primary_df.empty:
            idx_min = primary_df.index.min()
            overlap_start = idx_min.date() if hasattr(idx_min, "date") else start
        else:
            overlap_start = start
        try:
            fb_df = self._fallback.fetch(symbol, overlap_start, end)
        except Exception as exc:
            logger.warning(
                "fallback overlap fetch failed; skipping reconciliation",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return False
        report = reconcile(
            primary_df,
            fb_df,
            self._primary.name,
            self._fallback.name,
            symbol=symbol,
            window_days=_OVERLAP_DAYS,
        )
        return report.max_close_diff_pct > 1.0 or report.split_disagreement

    # --- parquet cache (TTL) ---

    def _cache_path(self, symbol: str, start: date, end: date) -> Path | None:
        if self._cache_dir is None:
            return None
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        name = f"{symbol}_{start.isoformat()}_{end.isoformat()}.parquet"
        return self._cache_dir / name

    def _read_cache(self, symbol: str, start: date, end: date) -> OHLCVResult | None:
        path = self._cache_path(symbol, start, end)
        if path is None or not path.exists():
            return None
        age_hours = (time.time() - path.stat().st_mtime) / 3600.0
        if age_hours >= self._cache_ttl_hours:
            return None
        df = pd.read_parquet(path)
        return OHLCVResult(symbol, df, self._primary.name, False, False, True)

    def _write_cache(
        self, symbol: str, start: date, end: date, result: OHLCVResult
    ) -> None:
        path = self._cache_path(symbol, start, end)
        if path is None or result.df is None:
            return
        result.df.to_parquet(path)
