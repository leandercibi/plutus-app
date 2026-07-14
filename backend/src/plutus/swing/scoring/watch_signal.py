from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.config.settings import Settings

# Lives in the swing.scoring layer (not scheduler.jobs) so both the API layer
# (quick-score) and the pipeline layer can reuse it without violating the
# Domain layering contract (00_principles §3) — scheduler sits above api, so
# api/pipeline may not import from scheduler.


class _FallbackCalibration:
    """Zero-sample calibration — uses drawn_rr fallback gate (n < min_n_low)."""

    _POOLED: dict[str, float] = {"target_1": 0.55, "target_2": 0.25, "stop": 0.35}

    def hit_rate(self, bundle: str, regime: str, target_field: str) -> float:
        return self._POOLED.get(target_field, 0.5)

    def confidence_band(
        self, bundle: str, regime: str, score_bucket: str
    ) -> Literal["low", "medium", "high"]:
        return "low"

    def n_for(self, bundle: str, regime: str) -> int:
        return 0


def _delivery_df_from_db(
    symbol: str, session: Session, as_of: date, lookback_days: int = 30
) -> pd.DataFrame:
    """Build the flow pillar's delivery history from daily_delivery_fetch_job's stored
    data — ascending by date, last row = most recent (what DeliveryTrend treats as
    "today"). Empty DataFrame if nothing's been fetched yet for this symbol."""
    from plutus.db.models import DailyDelivery

    rows = (
        session.execute(
            select(DailyDelivery)
            .where(DailyDelivery.symbol == symbol, DailyDelivery.as_of_date <= as_of)
            .order_by(DailyDelivery.as_of_date.desc())
            .limit(lookback_days)
        )
        .scalars()
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["delivery_qty", "traded_qty", "delivery_pct"])
    rows = sorted(rows, key=lambda r: r.as_of_date)
    return pd.DataFrame(
        {
            "delivery_qty": [r.delivery_qty for r in rows],
            "traded_qty": [r.traded_qty for r in rows],
            "delivery_pct": [r.delivery_pct for r in rows],
        }
    )


def _make_watch_signal(
    symbol: str,
    candles: pd.DataFrame,
    regime_label: str,
    run_id: str,
    now: datetime,
    cost_model: Any,
    calibration: Any,
    settings: Settings,
    *,
    v4_pillars: Any | None = None,  # composite_v4.V4Pillars | None
    fundamentals_hard_avoid: bool = False,
    fundamentals_pts: int = 0,
    flow_pts: int = 0,
) -> Any | None:
    """Light momentum pre-screen → returns an unsaved SwingSignal or None.

    Passes when ≥2 of 3 criteria are met:
      1. RSI 45-70 (building momentum, not overbought)
      2. MACD histogram positive
      3. Price within 5% of 20-day high (approaching breakout zone)

    When ``v4_pillars`` is provided AND ``settings.enable_v4_selection`` is True
    the composite score adds the RS / flow / continuous-regime pillars.
    """
    from plutus.db.models import SwingSignal
    from plutus.shared.scoring_inputs import ExpectancyInputs
    from plutus.swing.scoring.classifier import classify
    from plutus.swing.scoring.composite_v4 import (
        V4Pillars,
        legacy_regime_pillar,
        pillar_breakdown,
    )
    from plutus.swing.scoring.composite_v4 import (
        composite_score as _composite,
    )
    from plutus.swing.scoring.expectancy import compute_expectancy
    from plutus.swing.scoring.pillars import _macd_components, _rsi, technical_score

    close = candles["close"]
    if len(close) < 21:
        return None

    price = float(close.iloc[-1])
    rsi = _rsi(close)
    _, _, macd_h = _macd_components(close)
    macd_pos = bool(macd_h > 0)
    high_20d = float(candles["high"].iloc[-21:-1].max())
    near_high = price >= high_20d * 0.95

    if sum([45 <= rsi <= 70, macd_pos, near_high]) < 2:
        return None

    from plutus.swing.bundles._indicators import atr as _atr

    atr_series = _atr(candles, 14)
    last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else price * 0.02
    entry = Decimal(str(round(price, 2)))
    stop = entry - Decimal(str(round(last_atr * 1.5, 2)))
    risk = entry - stop
    if risk <= 0:
        return None
    target_1 = entry + Decimal("1.5") * risk
    target_2 = entry + Decimal("2.5") * risk

    tech = technical_score(candles)
    exp = compute_expectancy(
        ExpectancyInputs(
            bundle="watch_screen",
            regime=regime_label,
            entry=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            qty=1,
        ),
        calibration,
        cost_model,
        settings,
    )
    if exp.expectancy_R < 0:
        return None

    exp_pillar = int(round(min(25.0, max(0.0, exp.expectancy_R / 2.0 * 25.0))))

    band = calibration.confidence_band("watch_screen", regime_label, "")

    if settings.enable_v4_selection and v4_pillars is not None:
        v4: V4Pillars = v4_pillars
        regime_pts = v4.regime_pts
        rs_pts = v4.rs_pts
        flow_pts = v4.flow_pts
        composite = _composite(
            technical_pts=tech.total,
            expectancy_pts=exp_pillar,
            regime_pts=regime_pts,
            rs_pts=rs_pts,
            flow_pts=flow_pts,
        )
        breakdown = pillar_breakdown(
            technical_pts=tech.total,
            expectancy_pts=exp_pillar,
            regime_pts=regime_pts,
            v4=v4,
            calibration_band=band,
            calibration_n=0,
            extras={
                "watch_criteria": {
                    "rsi_ok": 45 <= rsi <= 70,
                    "macd_pos": macd_pos,
                    "near_high": near_high,
                },
                "tradable": composite >= settings.score_floor_actionable,
            },
        )
    else:
        regime_pts = legacy_regime_pillar(regime_label)
        composite = tech.total + exp_pillar + regime_pts + fundamentals_pts + flow_pts
        breakdown = {
            "technical": tech.total,
            "expectancy": exp_pillar,
            "flow": flow_pts,
            "sentiment": 0,
            "regime_fit": regime_pts,
            "fundamentals": fundamentals_pts,
            "calibration_band": band,
            "calibration_n": 0,
            "watch_criteria": {
                "rsi_ok": 45 <= rsi <= 70,
                "macd_pos": macd_pos,
                "near_high": near_high,
            },
        }

    cls_out = classify(
        score=composite,
        expectancy=exp,
        calibration_band=band,
        settings=settings,
        hard_avoid=fundamentals_hard_avoid,
    )
    if cls_out.label == "AVOID":
        return None

    drawn_rr = float((target_1 - entry) / risk)
    return SwingSignal(
        run_id=run_id,
        symbol=symbol,
        bundle="watch_screen",
        score=composite,
        label=cls_out.label,
        entry=entry,
        stop_loss=stop,
        target_1=target_1,
        target_2=target_2,
        expectancy_R=exp.expectancy_R,
        drawn_rr=drawn_rr,
        regime_at_signal=regime_label,
        pillar_breakdown_json=breakdown,
        counterfactual_text=cls_out.counterfactual,
        created_at=now,
    )
