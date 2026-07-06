from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pandas as pd
import yfinance as yf

from plutus.shared.regime.detector import RegimeInputs

logger = logging.getLogger(__name__)

# ^NSEI is a cash-market index — AngelOne doesn't expose it via candle API.
# yfinance is intentional here.
_NIFTY = "^NSEI"
_LOOKBACK = 210  # need 200d DMA + buffer


def _nifty_series(as_of: date) -> pd.Series:
    start = as_of - timedelta(days=_LOOKBACK)
    try:
        raw = yf.download(
            _NIFTY, start=start, end=as_of + timedelta(days=1), auto_adjust=True, progress=False
        )
        if raw.empty:
            raise ValueError("empty")
        s = raw["Close"].squeeze()
        s.index = pd.to_datetime(s.index).normalize()
        return cast(pd.Series, s.sort_index())
    except Exception as exc:
        logger.warning("NIFTY download failed: %s", exc)
        return pd.Series(dtype=float)


def build_regime_inputs(
    as_of: date,
    vix_provider: object,
    breadth_provider: object,
    fii_dii_provider: object,
) -> RegimeInputs:
    nifty = _nifty_series(as_of)

    if nifty.empty or len(nifty) < 10:
        logger.warning("Insufficient NIFTY data; returning neutral RegimeInputs")
        return _neutral(as_of)

    nifty_close = Decimal(str(float(nifty.iloc[-1])))
    nifty_50dma = Decimal(str(float(nifty.rolling(50, min_periods=25).mean().iloc[-1])))
    nifty_200dma = Decimal(str(float(nifty.rolling(200, min_periods=100).mean().iloc[-1])))

    window_start = as_of - timedelta(days=60)
    pct50 = float(breadth_provider.fetch_pct_above_dma(50, window_start, as_of).iloc[-1])  # type: ignore[attr-defined]
    pct200 = float(breadth_provider.fetch_pct_above_dma(200, window_start, as_of).iloc[-1])  # type: ignore[attr-defined]
    ad = float(breadth_provider.fetch_advance_decline(window_start, as_of).iloc[-1])  # type: ignore[attr-defined]

    # 5 trading days ago
    past_idx = nifty.index[nifty.index <= pd.Timestamp(as_of)]
    pct50_5d_ago = pct50
    if len(past_idx) >= 6:
        d5 = past_idx[-6].date()
        s5 = breadth_provider.fetch_pct_above_dma(50, d5 - timedelta(days=1), d5)  # type: ignore[attr-defined]
        if not s5.empty:
            pct50_5d_ago = float(s5.iloc[-1])

    vix = float(vix_provider.latest())  # type: ignore[attr-defined]

    fii_df = fii_dii_provider.fetch(as_of - timedelta(days=10), as_of)  # type: ignore[attr-defined]
    _CRORE = 10_000_000
    fii_5d = (
        Decimal(str(float(fii_df["fii_net_inr_crore"].tail(5).sum() * _CRORE)))
        if not fii_df.empty
        else Decimal("0")
    )
    dii_5d = (
        Decimal(str(float(fii_df["dii_net_inr_crore"].tail(5).sum() * _CRORE)))
        if not fii_df.empty
        else Decimal("0")
    )

    return RegimeInputs(
        nifty_close=nifty_close,
        nifty_50dma=nifty_50dma,
        nifty_200dma=nifty_200dma,
        pct_above_50dma=pct50,
        pct_above_200dma=pct200,
        advance_decline=ad,
        india_vix=vix,
        fii_flow_5d_sum_inr=fii_5d,
        dii_flow_5d_sum_inr=dii_5d,
        pct_above_50dma_5d_ago=pct50_5d_ago,
    )


def _neutral(as_of: date) -> RegimeInputs:
    v = Decimal("20000")
    return RegimeInputs(
        nifty_close=v,
        nifty_50dma=v,
        nifty_200dma=v,
        pct_above_50dma=0.5,
        pct_above_200dma=0.5,
        advance_decline=1.0,
        india_vix=15.0,
        fii_flow_5d_sum_inr=Decimal("0"),
        dii_flow_5d_sum_inr=Decimal("0"),
        pct_above_50dma_5d_ago=0.5,
    )
