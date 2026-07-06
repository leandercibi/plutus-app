from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_FINANCIAL_KEYWORDS = ("bank", "financ", "insurance", "nbfc", "capital market")


@dataclass(frozen=True)
class FundamentalsData:
    """Fundamental data fetched from yfinance for a single NSE symbol."""

    pe_ttm: float | None  # trailing P/E; None if not available
    pe_5y_median: float | None  # 5-year median P/E; falls back to pe_ttm
    ev_ebitda: float | None  # enterprise-value / EBITDA ratio
    de: float  # debt/equity ratio (0 when unavailable)
    roce: float  # ROE used as ROCE proxy; fractional (0.18 = 18%)
    fcf_margin: float  # free-cash-flow / revenue; fractional
    is_financial: bool  # true for banks / NBFCs / insurance
    eps_history: pd.DataFrame  # columns: year (int), eps (float); oldest first


class FundamentalsProvider:
    """Fetch fundamental data for NSE symbols via yfinance.

    Each ticker.info call is ~0.5–1 s; the in-process yfinance HTTP cache
    makes repeated calls for the same ticker essentially free within one run.
    """

    def fetch(self, symbol: str) -> FundamentalsData:
        import yfinance as yf

        ticker_sym = symbol if "." in symbol else f"{symbol}.NS"
        try:
            ticker = yf.Ticker(ticker_sym)
            info: dict[str, Any] = ticker.info or {}
        except Exception as exc:
            logger.warning("yfinance info failed for %s: %s", symbol, exc)
            return _empty()

        pe_ttm = _f(info.get("trailingPE"))
        ev_ebitda = _f(info.get("enterpriseToEbitda"))

        # yfinance returns debtToEquity as a percentage: 45.2 means D/E = 0.452
        de_raw = _f(info.get("debtToEquity"), default=0.0) or 0.0
        de = de_raw / 100.0 if de_raw > 10.0 else de_raw

        # returnOnEquity is fractional (0.18 = 18%); guard against rare % form
        roe_raw = _f(info.get("returnOnEquity"), default=0.0) or 0.0
        roce = roe_raw / 100.0 if roe_raw > 1.0 else roe_raw

        revenue = _f(info.get("totalRevenue"))
        fcf = _f(info.get("freeCashflow"))
        fcf_margin = float(fcf / revenue) if (fcf and revenue and revenue > 0) else 0.0

        sector = (info.get("sector") or info.get("industry") or "").lower()
        is_financial = any(k in sector for k in _FINANCIAL_KEYWORDS)

        eps_df = _build_eps_df(ticker, info)

        # yfinance does not expose historical PE — use current PE as 5-year median.
        # This means the cheapness discount = 0, which is conservative but correct.
        pe_5y_median = pe_ttm

        return FundamentalsData(
            pe_ttm=pe_ttm,
            pe_5y_median=pe_5y_median,
            ev_ebitda=ev_ebitda,
            de=de,
            roce=roce,
            fcf_margin=fcf_margin,
            is_financial=is_financial,
            eps_history=eps_df,
        )


def _build_eps_df(ticker: Any, info: dict[str, Any]) -> pd.DataFrame:
    """Construct annual EPS DataFrame from yfinance income statement."""
    shares = _f(info.get("sharesOutstanding")) or _f(info.get("impliedSharesOutstanding"))
    if not shares or shares <= 0:
        return pd.DataFrame(columns=["year", "eps"])

    try:
        fin = ticker.financials  # columns = fiscal-year dates, most-recent first
        if fin is None or fin.empty:
            return pd.DataFrame(columns=["year", "eps"])

        net_income_row = None
        for idx in fin.index:
            if "net income" in str(idx).lower():
                net_income_row = fin.loc[idx]
                break
        if net_income_row is None:
            return pd.DataFrame(columns=["year", "eps"])

        rows = []
        for col in fin.columns:
            val = _f(net_income_row.get(col))
            if val is None:
                continue
            year = col.year if hasattr(col, "year") else int(str(col)[:4])
            rows.append({"year": year, "eps": val / shares})

        if not rows:
            return pd.DataFrame(columns=["year", "eps"])

        return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    except Exception as exc:
        logger.debug("EPS history build failed: %s", exc)
        return pd.DataFrame(columns=["year", "eps"])


def _f(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        f = float(val)
        return default if not np.isfinite(f) else f
    except (TypeError, ValueError):
        return default


def _empty() -> FundamentalsData:
    return FundamentalsData(
        pe_ttm=None,
        pe_5y_median=None,
        ev_ebitda=None,
        de=0.0,
        roce=0.0,
        fcf_margin=0.0,
        is_financial=False,
        eps_history=pd.DataFrame(columns=["year", "eps"]),
    )
