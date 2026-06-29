from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy.orm import Session

from plutus.alerts.channels import AlertMessage
from plutus.alerts.factory import build_alert_monitor
from plutus.config.settings import Settings, get_settings
from plutus.data.freshness import assert_freshness
from plutus.data.providers.market_data import (
    compute_advance_decline,
    compute_breadth_from_candles,
    fetch_india_vix,
    fetch_nifty_candles,
)
from plutus.data.providers.nse500 import NSE500_SYMBOLS
from plutus.data.ohlcv import OHLCVChain
from plutus.data.providers.yfinance_provider import YFinanceProvider
from plutus.db.models import RegimeSnapshot, SwingSignal
from plutus.db.session import session_scope
from plutus.shared.calibration.protocol import CalibrationLookup
from plutus.shared.cost_model.costs import CostModel
from plutus.shared.regime.detector import RegimeDetector, RegimeInputs
from plutus.swing.bundles.base import BundleContext
from plutus.swing.bundles.breakout import BreakoutBundle
from plutus.swing.bundles.reversal import ReversalBundle
from plutus.swing.bundles.trend import TrendBundle
from plutus.swing.bundles.vcp import VCPBundle
from plutus.swing.scoring.classifier import classify
from plutus.swing.scoring.expectancy import ExpectancyInputs, compute_expectancy
from plutus.swing.scoring.pillars import technical_score
from plutus.swing.scoring.selector import BundleRegimeStat, SelectorInputs

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    signals_written: int
    symbols_processed: int
    errors: list[str] = field(default_factory=list)


class _FallbackCalibration:
    """Sensible defaults when no calibration rows exist yet."""

    def hit_rate(self, bundle: str, regime: str, target_field: str) -> float:
        return {"target_1": 0.50, "target_2": 0.25, "stop": 0.40}.get(target_field, 0.40)

    def confidence_band(self, bundle: str, regime: str, score_bucket: str) -> str:
        return "low"

    def n_for(self, bundle: str, regime: str) -> int:
        return 0


def _build_ohlcv_chain(cfg: Settings) -> OHLCVChain:
    """AngelOne primary → yfinance fallback. Falls back silently if credentials absent."""
    primary: object = YFinanceProvider()
    if all([cfg.angel_api_key, cfg.angel_client_id, cfg.angel_password, cfg.angel_totp_secret]):
        try:
            from plutus.data.providers.angelone_provider import AngelOneProvider
            primary = AngelOneProvider(
                api_key=cfg.angel_api_key,
                client_id=cfg.angel_client_id,
                password=cfg.angel_password,
                totp_secret=cfg.angel_totp_secret,
            )
        except Exception:
            primary = YFinanceProvider()
    return OHLCVChain(primary=primary, fallback=YFinanceProvider())  # type: ignore[arg-type]


def _fetch_candles(symbol: str, end: date, chain: OHLCVChain) -> pd.DataFrame | None:
    start = end - timedelta(days=_LOOKBACK_DAYS)
    try:
        result = chain.fetch(symbol, start, end)
        if not result.success or result.df is None or result.df.empty or len(result.df) < 60:
            return None
        return result.df
    except Exception as exc:
        logger.warning("candle fetch failed", extra={"symbol": symbol, "error": str(exc)})
        return None


def _delivery_stub(candles: pd.DataFrame) -> pd.DataFrame:
    """40% delivery_pct stub until real NSE bhav copy is wired."""
    df = candles[["date", "volume"]].copy()
    df["delivery_qty"] = (df["volume"] * 0.4).astype(int)
    df["traded_qty"] = df["volume"].astype(int)
    df["delivery_pct"] = 0.4
    return df.reset_index(drop=True)


def _detect_regime(
    nifty_df: pd.DataFrame,
    all_candles: dict[str, pd.DataFrame],
    vix: float,
    as_of: date,
    cfg: Settings,
) -> tuple[RegimeInputs, str]:
    nifty_close = Decimal(str(float(nifty_df["close"].iloc[-1])))
    nifty_dma50 = Decimal(str(float(nifty_df["close"].rolling(50).mean().iloc[-1])))
    nifty_dma200 = Decimal(str(float(nifty_df["close"].rolling(200).mean().iloc[-1])))
    pct50, pct200 = compute_breadth_from_candles(all_candles, 50, as_of)
    ad = compute_advance_decline(all_candles, as_of)
    inputs = RegimeInputs(
        nifty_close=nifty_close,
        nifty_50dma=nifty_dma50,
        nifty_200dma=nifty_dma200,
        pct_above_50dma=pct50,
        pct_above_200dma=pct200,
        advance_decline=ad,
        india_vix=vix,
        fii_flow_5d_sum_inr=Decimal("0"),
        dii_flow_5d_sum_inr=Decimal("0"),
        pct_above_50dma_5d_ago=pct50 * 0.98,
    )
    verdict = RegimeDetector(cfg).classify(inputs)
    return inputs, verdict.label


def _persist_regime(session: Session, inputs: RegimeInputs, label: str, vix: float, as_of: date) -> None:
    existing = session.query(RegimeSnapshot).filter_by(as_of_date=as_of).first()
    if existing:
        return
    session.add(RegimeSnapshot(
        as_of_date=as_of,
        label=label,
        nifty_close=inputs.nifty_close,
        pct_above_50dma=inputs.pct_above_50dma,
        pct_above_200dma=inputs.pct_above_200dma,
        advance_decline=inputs.advance_decline,
        india_vix=vix,
        fii_flow_inr=Decimal("0"),
        dii_flow_inr=Decimal("0"),
    ))


def _build_selector_inputs(session: Session, regime: str, cfg: Settings) -> SelectorInputs:
    from plutus.db.models import BundleStatPerRegime
    rows = session.query(BundleStatPerRegime).filter_by(regime=regime).all()
    stats = {
        (r.bundle, r.regime): BundleRegimeStat(
            bundle=r.bundle, regime=r.regime,
            oos_sharpe_shrunk=r.oos_sharpe_shrunk, n_trades=r.n_trades,
        )
        for r in rows
    }
    return SelectorInputs(pooled_oos_stats=stats, min_n=cfg.bundle_min_n)


def _score_and_classify(
    sym: str,
    candles: pd.DataFrame,
    best_signal: object,
    regime: str,
    calibration: CalibrationLookup,
    cost_model: CostModel,
    cfg: Settings,
) -> dict | None:
    from plutus.shared.types import BundleSignal
    sig: BundleSignal = best_signal  # type: ignore[assignment]
    exp_inputs = ExpectancyInputs(
        bundle=sig.bundle,
        regime=regime,
        entry=sig.entry,
        stop_loss=sig.stop_loss,
        target_1=sig.target_1,
        target_2=sig.target_2,
        qty=100,
    )
    exp_result = compute_expectancy(exp_inputs, calibration, cost_model, cfg)
    if not exp_result.passes_primary_gate and not exp_result.passes_fallback_gate:
        return None

    tech = technical_score(candles)
    exp_score = int(min(25, max(0, exp_result.expectancy_R * 20)))
    regime_score = {"BULL": 13, "BEAR": 4, "SIDEWAYS": 8}.get(regime, 8)
    pillar_bd = {
        "technical": tech.total,
        "expectancy": exp_score,
        "flow": 8,
        "sentiment": 3,
        "regime_fit": regime_score,
        "fundamentals": 6,
        "calibration_n": calibration.n_for(sig.bundle, regime),
        "calibration_band": calibration.confidence_band(sig.bundle, regime, ""),
    }
    score_keys = ("technical", "expectancy", "flow", "sentiment", "regime_fit", "fundamentals")
    total_score = sum(pillar_bd[k] for k in score_keys)
    clf = classify(total_score, exp_result, pillar_bd["calibration_band"], cfg)  # type: ignore[arg-type]
    return {
        "signal": sig,
        "score": total_score,
        "label": clf.label,
        "expectancy_R": exp_result.expectancy_R,
        "drawn_rr": exp_result.drawn_rr,
        "pillar_bd": pillar_bd,
        "counterfactual": clf.counterfactual or None,
    }


def run_sunday_pipeline(
    as_of: date | None = None,
    symbols: list[str] | None = None,
    settings: Settings | None = None,
) -> PipelineResult:
    """Full Sunday pipeline: fetch → regime → bundles → signals → DB → alerts."""
    cfg = settings or get_settings()
    run_id = f"sun-{uuid.uuid4().hex[:8]}"
    as_of = as_of or date.today()
    symbols = symbols or NSE500_SYMBOLS

    logger.info("pipeline starting", extra={"run_id": run_id, "as_of": str(as_of)})

    # 1. Nifty + VIX — index tickers (^NSEI, ^INDIAVIX) via yfinance; AngelOne doesn't expose them
    try:
        nifty_df = fetch_nifty_candles(end=as_of)
        vix = fetch_india_vix(end=as_of)
    except Exception as exc:
        return PipelineResult(run_id, 0, 0, [f"nifty/vix: {exc}"])

    # 2. Universe candles — AngelOne primary, yfinance fallback
    chain = _build_ohlcv_chain(cfg)
    all_candles: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = _fetch_candles(sym, as_of, chain)
        if df is not None:
            all_candles[sym] = df
    if not all_candles:
        return PipelineResult(run_id, 0, 0, ["no candles"])

    # 3. Freshness
    latest_date = max(df["date"].iloc[-1].date() for df in all_candles.values())
    try:
        assert_freshness(latest_date, as_of, enabled=cfg.freshness_assert_enabled)
    except Exception as exc:
        return PipelineResult(run_id, 0, len(all_candles), [f"freshness: {exc}"])

    # 4. Regime
    regime_inputs, regime_label = _detect_regime(nifty_df, all_candles, vix, as_of, cfg)

    # 5. Bundles + scoring
    bundles = [TrendBundle(cfg), BreakoutBundle(cfg), ReversalBundle(cfg), VCPBundle(cfg)]
    calibration: CalibrationLookup = _FallbackCalibration()  # type: ignore[assignment]
    cost_model = CostModel(cfg)
    errors: list[str] = []
    results = []

    for sym, candles in all_candles.items():
        try:
            ctx = BundleContext(symbol=sym, regime=regime_label, delivery=_delivery_stub(candles))
            sub_signals = [sig for b in bundles for sig in [b.fit_signal(sym, candles, ctx)] if sig]
            if not sub_signals:
                continue
            best = sub_signals[0]
            scored = _score_and_classify(sym, candles, best, regime_label, calibration, cost_model, cfg)
            if scored:
                results.append(scored)
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            logger.error("symbol error", extra={"symbol": sym, "error": str(exc)})

    # 6. Persist
    with session_scope() as session:
        _persist_regime(session, regime_inputs, regime_label, vix, as_of)
        for r in results:
            sig = r["signal"]
            session.add(SwingSignal(
                run_id=run_id,
                symbol=sig.symbol,
                bundle=sig.bundle,
                score=r["score"],
                label=r["label"],
                entry=sig.entry,
                stop_loss=sig.stop_loss,
                target_1=sig.target_1,
                target_2=sig.target_2,
                expectancy_R=r["expectancy_R"],
                drawn_rr=r["drawn_rr"],
                regime_at_signal=regime_label,
                pillar_breakdown_json=r["pillar_bd"],
                counterfactual_text=r["counterfactual"],
       created_at=datetime.utcnow(),
            ))

    # 7. Telegram digest
    with session_scope() as session:
        monitor = build_alert_monitor(cfg)
        monitor.emit(
            AlertMessage(
                kind="ENTRY",
                symbol=None,
                title=f"Sunday run: {regime_label} — {len(results)} signals",
                body_md=(
                    f"Processed {len(all_candles)} symbols. "
                    f"{len(results)} signals generated. "
                    f"Regime: {regime_label}. Errors: {len(errors)}."
                ),
                severity="INFO",
                deduplication_key=f"SUNDAY:{run_id}",
            ),
            now=datetime.utcnow(),
            session=session,
        )

    logger.info("pipeline done", extra={"run_id": run_id, "signals": len(results), "errors": len(errors)})
    return PipelineResult(run_id, len(results), len(all_candles), errors)
