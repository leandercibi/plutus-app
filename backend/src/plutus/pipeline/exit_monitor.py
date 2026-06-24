from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from plutus.alerts.factory import build_alert_monitor
from plutus.alerts.formatter import AlertFormatter
from plutus.config.settings import Settings, get_settings
from plutus.data.providers.yfinance_provider import YFinanceProvider
from plutus.db.models import Fill, SwingSignal, SwingTrade
from plutus.db.session import session_scope
from plutus.shared.cost_model.costs import CostModel
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy
from plutus.shared.fills.types import OHLCBar, TradePlan

logger = logging.getLogger(__name__)


def _latest_bar(symbol: str, as_of: date) -> OHLCBar | None:
    start = as_of - timedelta(days=10)
    try:
        df = YFinanceProvider().fetch(symbol, start, as_of)
        if df.empty:
            return None
        row = df.iloc[-1]
        return OHLCBar(
            as_of=row["date"].date() if hasattr(row["date"], "date") else as_of,
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
        )
    except Exception as exc:
        logger.warning("price fetch failed", extra={"symbol": symbol, "error": str(exc)})
        return None


def run_exit_monitor(
    as_of: date | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Check every open trade against today's prices; emit SL/T1 alerts."""
    cfg = settings or get_settings()
    as_of = as_of or date.today()
    slippage = SlippageModel(cfg)
    fill_policy = FillPolicy(slippage)
    cost_model = CostModel(cfg)
    formatter = AlertFormatter()
    monitor = build_alert_monitor(cfg)
    counts = {"sl_breach": 0, "t1_hit": 0, "errors": 0}

    with session_scope() as session:
        open_trades = (
            session.query(SwingTrade)
            .filter(SwingTrade.state.in_(["OPEN", "T1_HIT"]))
            .all()
        )
        for trade in open_trades:
            try:
                _check_trade(trade, as_of, fill_policy, cost_model, formatter, monitor, session, cfg, counts)
            except Exception as exc:
                counts["errors"] += 1
                logger.error("exit check failed", extra={"trade": trade.id, "error": str(exc)})

    return counts


def _check_trade(
    trade: SwingTrade,
    as_of: date,
    fill_policy: FillPolicy,
    cost_model: CostModel,
    formatter: AlertFormatter,
    monitor: object,
    session: Session,
    cfg: Settings,
    counts: dict[str, int],
) -> None:
    from typing import cast

    from plutus.alerts.monitor import AlertMonitor
    mon: AlertMonitor = cast(AlertMonitor, monitor)

    # Get the signal for stop/targets
    signal = session.query(SwingSignal).filter_by(id=trade.signal_id).first()
    if signal is None:
        return

    bar = _latest_bar(trade.symbol, as_of)
    if bar is None:
        return

    plan = TradePlan(
        symbol=trade.symbol,
        signal_date=signal.created_at.date(),
        entry=signal.entry,
        stop_loss=signal.stop_loss,
        target_1=signal.target_1,
        target_2=signal.target_2,
    )

    # Check stop loss
    stop_fill = fill_policy.fill_stop(plan, bar, adv=500_000, atr_pct=0.02)
    if stop_fill is not None and trade.state == "OPEN":
        risk_per_share = signal.entry - signal.stop_loss
        realized_R = float((stop_fill.price - signal.entry) / risk_per_share) if risk_per_share else 0.0
        trade.state = "CLOSED_LOSS"
        trade.closed_at = datetime.utcnow()
        trade.realized_R = realized_R
        trade.exit_reason = "SL_BREACH"
        session.add(Fill(
            trade_id=trade.id, kind="MOCK", side="SELL",
            qty=trade.qty, price=stop_fill.price,
            cost_inr=cost_model.sell_cost(trade.qty, stop_fill.price).total,
            slippage_bps=stop_fill.slippage_bps,
            filled_at=stop_fill.filled_at,
        ))
        msg = formatter.format_sl_breach(trade.symbol, stop_fill.price, as_of)
        mon.emit(msg, now=datetime.utcnow(), session=session)
        counts["sl_breach"] += 1
        logger.info("SL breach", extra={"symbol": trade.symbol, "price": str(stop_fill.price)})
        return

    # Check T1
    t1_fill = fill_policy.fill_target(plan, bar, target_level=1, adv=500_000, atr_pct=0.02)
    if t1_fill is not None and trade.state == "OPEN":
        trade.state = "T1_HIT"
        session.add(Fill(
            trade_id=trade.id, kind="MOCK", side="SELL",
            qty=trade.qty // 2,
            price=t1_fill.price,
            cost_inr=cost_model.sell_cost(trade.qty // 2, t1_fill.price).total,
            slippage_bps=t1_fill.slippage_bps,
            filled_at=t1_fill.filled_at,
        ))
        msg = formatter.format_t1_hit(trade.symbol, as_of)
        mon.emit(msg, now=datetime.utcnow(), session=session)
        counts["t1_hit"] += 1
        logger.info("T1 hit", extra={"symbol": trade.symbol})

    # Check T2 (only when already at T1_HIT state)
    if signal.target_2 is not None:
        t2_fill = fill_policy.fill_target(plan, bar, target_level=2, adv=500_000, atr_pct=0.02)
        if t2_fill is not None and trade.state == "T1_HIT":
            trade.state = "CLOSED_WIN"
            trade.closed_at = datetime.utcnow()
            risk_per_share = signal.entry - signal.stop_loss
            trade.realized_R = float((t2_fill.price - signal.entry) / risk_per_share) if risk_per_share else 0.0
            trade.exit_reason = "T2_HIT"
            session.add(Fill(
                trade_id=trade.id, kind="MOCK", side="SELL",
                qty=trade.qty - (trade.qty // 2),
                price=t2_fill.price,
                cost_inr=cost_model.sell_cost(trade.qty - (trade.qty // 2), t2_fill.price).total,
                slippage_bps=t2_fill.slippage_bps,
                filled_at=t2_fill.filled_at,
            ))
            msg = formatter.format_t2_hit(trade.symbol, as_of)
            mon.emit(msg, now=datetime.utcnow(), session=session)
            counts.setdefault("t2_hit", 0)
            counts["t2_hit"] += 1
            logger.info("T2 hit — trade closed", extra={"symbol": trade.symbol})
