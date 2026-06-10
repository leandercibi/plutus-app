# src/plutus/agents/scoring.py
"""
Deterministic weighted scoring rubric.

Five pillars, each 0–100, combined with fixed weights:
    Technical   40%
    Smart Money 15%
    Sentiment   15%
    Regime      15%
    Risk/Reward 15%

Public API:
    compute_score(...)  -> (ScoreBreakdown, Classification)
    technical_pillar(df, best_bundle_sharpe) -> float
    smart_money_pillar(fii, dii, mf) -> float
    sentiment_pillar(news) -> float
    regime_pillar(nifty_regime, sector, sector_rs) -> float
    rr_pillar(entry, stop, t1, t2) -> float
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


# ── Types ─────────────────────────────────────────────────────────────────

class Classification(str, Enum):
    BUY   = "BUY"
    WATCH = "WATCH"
    HOLD  = "HOLD"
    AVOID = "AVOID"


PILLAR_WEIGHTS: dict[str, float] = {
    "technical":   0.40,
    "smart_money": 0.15,
    "sentiment":   0.15,
    "regime":      0.15,
    "rr":          0.15,
}


@dataclass(frozen=True)
class ScoreBreakdown:
    technical:   float    # 0–100
    smart_money: float    # 0–100
    sentiment:   float    # 0–100
    regime:      float    # 0–100
    rr:          float    # 0–100
    hard_avoid_reasons: tuple = field(default_factory=tuple)

    @property
    def composite(self) -> int:
        weighted = sum(getattr(self, k) * w for k, w in PILLAR_WEIGHTS.items())
        return round(weighted)


# ── Classification thresholds ─────────────────────────────────────────────

BUY_THRESHOLD   = 70
WATCH_THRESHOLD = 55
HOLD_THRESHOLD  = 35


# ── Technical pillar (40%) ────────────────────────────────────────────────

def _trend_alignment(df: pd.DataFrame) -> float:
    """EMA stack alignment: fully bullish ⇒ 100, fully bearish ⇒ 0."""
    ema20  = df.get("EMA_20",  pd.Series(dtype=float))
    ema50  = df.get("EMA_50",  pd.Series(dtype=float))
    ema200 = df.get("EMA_200", pd.Series(dtype=float))

    try:
        e20  = float(ema20.iloc[-1])  if len(ema20)  > 0 else None
        e50  = float(ema50.iloc[-1])  if len(ema50)  > 0 else None
        e200 = float(ema200.iloc[-1]) if len(ema200) > 0 else None
    except (IndexError, TypeError):
        return 50.0

    if e50 is None:
        return 50.0

    score = 0.0
    # Short-term trend (EMA20 vs EMA50)
    if e20 is not None:
        if e20 > e50:
            score += 50.0
        else:
            score += 0.0
    else:
        score += 25.0  # neutral when unavailable

    # Medium-term trend (EMA50 vs EMA200)
    if e200 is not None:
        if e50 > e200:
            score += 50.0
        else:
            score += 0.0
    else:
        score += 25.0  # neutral when unavailable (e.g., < 200 bars)

    return score


def _momentum(df: pd.DataFrame) -> float:
    """RSI-based momentum score."""
    rsi_col = "RSI_14"
    if rsi_col not in df.columns or df[rsi_col].dropna().empty:
        return 50.0

    rsi = float(df[rsi_col].dropna().iloc[-1])
    uptrend = _trend_alignment(df) >= 50

    if rsi >= 70:
        return 50.0          # overbought caution
    elif rsi >= 60:
        return 80.0 + (rsi - 60) * 2.0   # 80–100 for RSI 60–70
    elif rsi >= 50:
        return 60.0 + (rsi - 50) * 2.0   # 60–80 for RSI 50–60
    elif rsi >= 40:
        return 40.0 + (rsi - 40) * 2.0   # 40–60 for RSI 40–50
    elif rsi >= 30:
        return 20.0 + (rsi - 30) * 2.0   # 20–40 for RSI 30–40
    else:
        # Oversold
        return 70.0 if uptrend else 10.0  # oversold-in-uptrend bonus


def _volume_confirmation(df: pd.DataFrame) -> float:
    """Volume surge vs 20-day average."""
    if "Volume_Ratio" not in df.columns:
        return 50.0
    vr_series = df["Volume_Ratio"].dropna()
    if vr_series.empty:
        return 50.0
    vr = float(vr_series.iloc[-1])
    if vr >= 1.5:
        return 100.0
    elif vr >= 1.3:
        return 70.0
    elif vr >= 1.0:
        return 50.0
    else:
        return max(0.0, vr / 1.0 * 50.0)


def _macd_signal(df: pd.DataFrame) -> float:
    """MACD histogram direction signal."""
    hist_col = "MACDh_12_26_9"
    if hist_col not in df.columns:
        return 50.0
    hist = df[hist_col].dropna()
    if len(hist) < 2:
        return 50.0
    h_now  = float(hist.iloc[-1])
    h_prev = float(hist.iloc[-2])
    if h_now > 0 and h_now > h_prev:
        return 100.0
    elif h_now > 0:
        return 70.0
    elif h_now < 0 and h_now < h_prev:
        return 0.0
    elif h_now < 0:
        return 30.0
    return 50.0


def _backtest_validation(best_sharpe: float) -> float:
    """Map best-bundle Sharpe [-2, +3] → 0–100."""
    clamped = max(-2.0, min(3.0, best_sharpe))
    return (clamped + 2.0) / 5.0 * 100.0


def technical_pillar(df: pd.DataFrame, best_bundle_sharpe: float = 0.0) -> float:
    """Weighted combination of 5 sub-components, returns 0–100."""
    trend = _trend_alignment(df)     # 30% weight
    mom   = _momentum(df)            # 25%
    vol   = _volume_confirmation(df) # 15%
    macd  = _macd_signal(df)        # 15%
    bt    = _backtest_validation(best_bundle_sharpe)  # 15%

    score = (
        trend * 0.30 +
        mom   * 0.25 +
        vol   * 0.15 +
        macd  * 0.15 +
        bt    * 0.15
    )
    return round(max(0.0, min(100.0, score)), 2)


# ── Smart Money pillar (15%) ──────────────────────────────────────────────

def smart_money_pillar(fii: dict, dii: dict, mf: dict) -> float:
    """Institutional flow bias + MF holdings delta."""
    fii_sig = (fii or {}).get("fii_signal", "unknown")
    dii_sig = (dii or {}).get("dii_signal", "unknown")
    mf_verdict = (mf or {}).get("verdict", "UNKNOWN")

    # Institutional flow bias (60% of pillar)
    if fii_sig == "net_buyer" and dii_sig == "net_buyer":
        flow_score = 100.0
    elif fii_sig == "net_buyer" or dii_sig == "net_buyer":
        flow_score = 65.0
    elif fii_sig == "net_seller" and dii_sig == "net_seller":
        flow_score = 0.0
    elif fii_sig == "net_seller" or dii_sig == "net_seller":
        flow_score = 35.0
    else:
        flow_score = 50.0

    # MF holdings delta (40% of pillar)
    if mf_verdict == "ACCUMULATING":
        mf_score = 90.0
    elif mf_verdict == "REDUCING":
        mf_score = 10.0
    elif mf_verdict == "NEUTRAL":
        mf_score = 50.0
    else:
        # UNKNOWN — graceful degradation, no penalty
        mf_score = 50.0

    score = flow_score * 0.60 + mf_score * 0.40
    return round(max(0.0, min(100.0, score)), 2)


# ── Sentiment pillar (15%) ────────────────────────────────────────────────

def sentiment_pillar(news: dict) -> tuple[float, list[str]]:
    """Maps sentiment score to 0–100. Returns (score, hard_avoid_reasons)."""
    news = news or {}
    raw     = float(news.get("sentiment_score", 0) or 0)
    label   = (news.get("sentiment_label") or "neutral").lower()
    material = bool(news.get("is_material_event") or news.get("is_material"))
    event_type = (news.get("material_event_type") or "").lower()

    hard_avoids: list[str] = []

    # Hard rule: negative material event → 0, emit hard avoid
    negative = "negative" in label or raw < -1.0
    if material and negative:
        hard_avoids.append("material_negative_event")
        return 0.0, hard_avoids

    # Linear map: -5..+5 → 0..100
    score = (raw + 5.0) / 10.0 * 100.0
    score = max(0.0, min(100.0, score))

    # Positive material: cap at 85 (volatility risk even on good news)
    if material and not negative:
        score = min(85.0, score)

    return round(score, 2), hard_avoids


# ── Regime pillar (15%) ───────────────────────────────────────────────────

def regime_pillar(nifty_regime: dict, sector: Optional[str], sector_rs: dict) -> float:
    """Nifty trend + sector RS rank. Returns 0–100."""
    nifty_regime = nifty_regime or {}
    trend  = nifty_regime.get("trend", "UNKNOWN")
    slope  = float(nifty_regime.get("slope", 0) or 0)

    # Nifty component (60%)
    if trend == "BULL":
        normalized_slope = min(1.0, abs(slope) / 0.01)  # 1% threshold
        nifty_score = 90.0 + 10.0 * normalized_slope
    elif trend == "BEAR":
        nifty_score = max(0.0, 30.0 - abs(slope) / 0.01 * 30.0)
    elif trend == "SIDEWAYS":
        nifty_score = 50.0
    else:
        nifty_score = 50.0  # UNKNOWN → neutral

    # Sector RS component (40%)
    sector_rs = sector_rs or {}
    if not sector_rs or not sector:
        sector_score = 50.0
    else:
        n = len(sector_rs)
        if n == 0:
            sector_score = 50.0
        else:
            rs_value = sector_rs.get(sector)
            if rs_value is None:
                sector_score = 50.0
            else:
                # Rank by RS (highest = 1)
                sorted_rs = sorted(sector_rs.values(), reverse=True)
                rank = sorted_rs.index(rs_value) + 1  # 1-based
                # Top 3 → 100, top half → 75, bottom 3 → 0
                if rank <= 3:
                    sector_score = 100.0
                elif rank <= n // 2:
                    sector_score = 75.0
                elif rank > n - 3:
                    sector_score = 0.0
                else:
                    sector_score = 40.0

    score = nifty_score * 0.60 + sector_score * 0.40
    return round(max(0.0, min(100.0, score)), 2)


# ── Risk/Reward pillar (15%) ──────────────────────────────────────────────

def rr_pillar(entry: float, stop: float, t1: float, t2: float) -> float:
    """R:R floor at 1.5; linear ramp 1.5→2.5 gives 0→100."""
    try:
        risk   = abs(float(entry) - float(stop))
        reward = abs(float(t1) - float(entry))
    except (TypeError, ValueError):
        return 0.0

    if risk == 0 or entry == 0:
        return 0.0

    ratio = reward / risk
    if ratio < 1.5:
        return 0.0
    return min(100.0, (ratio - 1.5) * 100.0)


# ── Composite + classification ────────────────────────────────────────────

def _classify(
    breakdown: ScoreBreakdown,
    position_size: float,
    material_negative: bool,
    regime_bear: bool,
    rr_pillar_score: Optional[float] = None,
) -> Classification:
    """Apply classification thresholds and hard rules."""
    # Hard avoids override everything
    if material_negative or "material_negative_event" in breakdown.hard_avoid_reasons:
        return Classification.AVOID
    if breakdown.composite < HOLD_THRESHOLD:
        return Classification.AVOID

    rr = breakdown.rr if rr_pillar_score is None else rr_pillar_score

    if regime_bear:
        # Bear market: don't initiate new long positions (BUY → WATCH at best).
        # Still surface high-quality setups so the trader can act when regime turns.
        if breakdown.composite >= WATCH_THRESHOLD:
            return Classification.WATCH
        return Classification.HOLD

    if (
        breakdown.composite >= BUY_THRESHOLD
        and rr > 0
        and position_size > 0
    ):
        return Classification.BUY

    if breakdown.composite >= WATCH_THRESHOLD:
        return Classification.WATCH

    if breakdown.composite >= HOLD_THRESHOLD:
        return Classification.HOLD

    return Classification.AVOID


def compute_score(
    symbol: str,
    indicator_df: pd.DataFrame,
    levels: dict,
    news: dict,
    fii: dict,
    dii: dict,
    mf: dict,
    nifty_regime: dict,
    sector: Optional[str],
    sector_rs: dict,
    best_bundle_sharpe: float = 0.0,
    position_size: float = 1.0,
) -> tuple[ScoreBreakdown, Classification]:
    """
    Main entry point. Compute all five pillars and return (ScoreBreakdown, Classification).

    `levels` should contain: entry, stop, t1, t2 as floats.
    """
    tech = technical_pillar(indicator_df, best_bundle_sharpe)
    sm   = smart_money_pillar(fii, dii, mf)

    sent_score, hard_avoids = sentiment_pillar(news)
    reg  = regime_pillar(nifty_regime, sector, sector_rs)
    rr   = rr_pillar(
        entry=float(levels.get("entry", 0) or 0),
        stop =float(levels.get("stop", 0)  or 0),
        t1   =float(levels.get("t1", 0)    or 0),
        t2   =float(levels.get("t2", 0)    or 0),
    )

    breakdown = ScoreBreakdown(
        technical=tech,
        smart_money=sm,
        sentiment=sent_score,
        regime=reg,
        rr=rr,
        hard_avoid_reasons=tuple(hard_avoids),
    )

    material_negative = "material_negative_event" in hard_avoids
    regime_bear = (nifty_regime or {}).get("trend") == "BEAR"
    cls = _classify(breakdown, position_size, material_negative, regime_bear)

    return breakdown, cls
