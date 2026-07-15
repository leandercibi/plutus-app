from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.api.auth import require_token
from plutus.api.deps import get_db
from plutus.api.schemas.swing import (
    CooldownRowOut,
    EnterFromSignalIn,
    FillOut,
    ManualExitIn,
    PillarBreakdownOut,
    PostmortemOut,
    RealFillIn,
    SwingSignalOut,
    SwingTradeOut,
)
from plutus.db.models import (
    AlertCooldown,
    Fill,
    SwingSignal,
    SwingTrade,
    WeeklyPostmortem,
)
from plutus.shared.fills.real_fill import log_real_fill

router = APIRouter(prefix="/swing", tags=["swing"], dependencies=[Depends(require_token)])

_CLOSED_STATES = ("CLOSED_WIN", "CLOSED_LOSS", "SCRATCHED", "EXPIRED")


def _as_int(raw: dict[str, Any], key: str) -> int:
    return int(raw.get(key, 0))


def _as_float(raw: dict[str, Any], key: str) -> float:
    return float(raw.get(key, 0.0))


def _pillar_out(raw: dict[str, Any]) -> PillarBreakdownOut:
    return PillarBreakdownOut(
        technical=_as_int(raw, "technical"),
        expectancy=_as_float(raw, "expectancy"),
        flow=_as_int(raw, "flow"),
        regime_fit=_as_int(raw, "regime_fit"),
        fundamentals=_as_int(raw, "fundamentals"),
        sentiment=_as_int(raw, "sentiment"),
    )


def _signal_out(row: SwingSignal) -> SwingSignalOut:
    raw: dict[str, Any] = row.pillar_breakdown_json or {}
    band = raw.get("calibration_band", "low")
    if band not in ("low", "medium", "high"):
        band = "low"
    return SwingSignalOut(
        id=row.id,
        run_id=row.run_id,
        symbol=row.symbol,
        bundle=row.bundle,
        score=row.score,
        label=cast(Any, row.label),
        entry=row.entry,
        stop_loss=row.stop_loss,
        target_1=row.target_1,
        target_2=row.target_2,
        expectancy_R=row.expectancy_R,
        drawn_rr=row.drawn_rr,
        regime_at_signal=row.regime_at_signal,
        pillar_breakdown=_pillar_out(raw),
        counterfactual=row.counterfactual_text,
        calibration_band=cast(Any, band),
        created_at=row.created_at,
    )


@router.get("/signals", response_model=list[SwingSignalOut])
def list_signals(
    run_id: str | None = Query(default=None),
    label: str | None = Query(default=None),
    latest_run: bool = Query(default=False, description="Filter to the most recent run_id only"),
    dedup: bool = Query(
        default=False, description="Keep highest-scored signal per (symbol, bundle) pair"
    ),
    db: Session = Depends(get_db),
) -> list[SwingSignalOut]:
    stmt = select(SwingSignal)

    # If latest_run=true and no explicit run_id, resolve the most recent run_id
    if latest_run and run_id is None:
        latest = db.execute(
            select(SwingSignal.run_id).order_by(SwingSignal.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest is not None:
            run_id = latest

    if run_id is not None:
        stmt = stmt.where(SwingSignal.run_id == run_id)
    if label is not None:
        stmt = stmt.where(SwingSignal.label == label)
    stmt = stmt.order_by(SwingSignal.score.desc(), SwingSignal.id.desc())

    rows = db.execute(stmt).scalars().all()

    if dedup:
        # Keep the highest-scored row per (symbol, bundle) pair.
        # The query is already score DESC so first occurrence wins.
        seen: set[tuple[str, str]] = set()
        deduped = []
        for row in rows:
            key = (row.symbol, row.bundle)
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        rows = deduped

    return [_signal_out(r) for r in rows]


@router.get("/signals/{signal_id}", response_model=SwingSignalOut)
def get_signal(signal_id: int, db: Session = Depends(get_db)) -> SwingSignalOut:
    row = db.get(SwingSignal, signal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return _signal_out(row)


@router.get("/positions", response_model=list[SwingTradeOut])
def list_positions(db: Session = Depends(get_db)) -> list[SwingTradeOut]:
    cutoff = datetime.utcnow() - timedelta(days=7)
    stmt = (
        select(SwingTrade)
        .where(
            (SwingTrade.state == "OPEN")
            | (SwingTrade.state == "T1_HIT")
            | (
                SwingTrade.state.in_(_CLOSED_STATES)
                & (SwingTrade.closed_at.is_not(None))
                & (SwingTrade.closed_at >= cutoff)
            )
        )
        .order_by(SwingTrade.opened_at.desc(), SwingTrade.id.desc())
    )
    return [
        SwingTradeOut.model_validate(r, from_attributes=True)
        for r in db.execute(stmt).scalars().all()
    ]


@router.post("/trades/{trade_id}/fills/real", response_model=FillOut)
def post_real_fill(trade_id: int, body: RealFillIn, db: Session = Depends(get_db)) -> FillOut:
    trade = db.get(SwingTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade not found")
    fill = log_real_fill(
        trade_id=trade_id,
        side=body.side,
        qty=body.qty,
        price=body.price,
        filled_at=body.filled_at or datetime.utcnow(),
        cost_inr=body.cost_inr,
        session=db,
    )
    return FillOut.model_validate(fill, from_attributes=True)


@router.post("/signals/{signal_id}/enter", response_model=FillOut)
def enter_from_signal(
    signal_id: int, body: EnterFromSignalIn, db: Session = Depends(get_db)
) -> FillOut:
    """Create a SwingTrade + real entry fill from a signal in one shot.

    Called when the user sees a signal on the dashboard and logs a manual
    broker entry. Creates the trade record (state=OPEN) then the fill.
    """
    signal = db.get(SwingSignal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")

    risk_per_share = float(signal.entry - signal.stop_loss)
    if risk_per_share <= 0:
        raise HTTPException(status_code=422, detail="signal has zero or negative risk")

    filled_at = body.filled_at or datetime.utcnow()
    trade = SwingTrade(
        signal_id=signal_id,
        symbol=signal.symbol,
        bundle=signal.bundle,
        state="OPEN",
        opened_at=filled_at,
        qty=body.qty,
        risk_R=round(risk_per_share, 4),
    )
    db.add(trade)
    db.flush()

    fill = Fill(
        trade_id=trade.id,
        kind="REAL",
        side=body.side,
        qty=body.qty,
        price=body.price,
        cost_inr=body.cost_inr,
        filled_at=filled_at,
    )
    db.add(fill)
    db.flush()
    return FillOut.model_validate(fill, from_attributes=True)


@router.post("/trades/{trade_id}/exit/manual", response_model=SwingTradeOut)
def manual_exit(trade_id: int, body: ManualExitIn, db: Session = Depends(get_db)) -> SwingTradeOut:
    """Close a swing trade — fully by default, partially if ``body.qty`` < remaining.

    Every SELL (partial or full) writes a closing Fill row AND credits
    proportional realised R onto ``trade.realized_R``:

        r_slice = ((sell_price − avg_entry) / risk_per_share) × (qty_sold / original_qty)

    ``original_qty`` is the sum of BUY fills so the ratio stays stable across
    successive partials. Full exit additionally closes the trade and sets state
    from the accumulated realised R (>= 0 → CLOSED_WIN, else CLOSED_LOSS).
    Alerting is the monitor's job — nothing re-fires here.
    """
    from decimal import Decimal

    from plutus.db.models import LatestPrice

    trade = db.get(SwingTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade not found")

    if body.qty is not None and body.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")
    is_partial = body.qty is not None and body.qty < trade.qty
    sell_qty = cast(int, body.qty) if is_partial else trade.qty

    # Avg entry + original qty from BUY fills — the sizing snapshot against
    # which realised R is normalised. Falls back to signal.entry when the trade
    # has no fill rows (legacy pre-fill data) so we credit 0R without crashing.
    buys = list(
        db.execute(select(Fill).where(Fill.trade_id == trade.id, Fill.side == "BUY")).scalars()
    )
    signal = db.get(SwingSignal, trade.signal_id)
    original_qty = sum(f.qty for f in buys) if buys else trade.qty
    if buys and original_qty > 0:
        avg_entry = sum(float(f.price) * f.qty for f in buys) / original_qty
    else:
        avg_entry = float(signal.entry) if signal is not None else 0.0

    # Resolve sell price: caller's → latest cached LatestPrice → avg_entry as
    # last-resort so a full exit still closes cleanly (as a 0R scratch) rather
    # than 422ing when the price refresh job is stale. Partial exits require a
    # real price — silently scratching a partial would be misleading.
    if body.price is not None:
        sell_price = body.price
    else:
        latest = (
            db.execute(select(LatestPrice).where(LatestPrice.symbol == trade.symbol))
            .scalars()
            .first()
        )
        if latest is not None:
            sell_price = Decimal(str(latest.price))
        elif is_partial:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No cached price for {trade.symbol}; pass an explicit "
                    f"`price` in the request body for partial exits."
                ),
            )
        else:
            sell_price = Decimal(str(avg_entry))

    # risk_R on SwingTrade is ₹/share (entry − stop_loss). R-multiple for this
    # slice, then scaled by slice/original so full-position closes sum to 1× the
    # size-independent R and partials credit proportionally.
    r_slice = 0.0
    if trade.risk_R and trade.risk_R > 0 and original_qty > 0:
        r_multiple = (float(sell_price) - avg_entry) / trade.risk_R
        r_slice = r_multiple * (sell_qty / original_qty)

    db.add(
        Fill(
            trade_id=trade.id,
            kind="REAL",
            side="SELL",
            qty=sell_qty,
            price=sell_price,
            cost_inr=Decimal("0"),
            filled_at=datetime.utcnow(),
        )
    )
    trade.realized_R = (trade.realized_R or 0.0) + r_slice

    if is_partial:
        trade.qty -= sell_qty
        db.flush()
        return SwingTradeOut.model_validate(trade, from_attributes=True)

    # Full exit: close and set state from accumulated realised R.
    trade.qty = 0
    trade.state = "CLOSED_WIN" if (trade.realized_R or 0.0) >= 0 else "CLOSED_LOSS"
    trade.closed_at = datetime.utcnow()
    trade.exit_reason = body.reason
    db.flush()
    return SwingTradeOut.model_validate(trade, from_attributes=True)


@router.get("/postmortem/latest", response_model=PostmortemOut)
def latest_postmortem(db: Session = Depends(get_db)) -> PostmortemOut:
    row = (
        db.execute(select(WeeklyPostmortem).order_by(WeeklyPostmortem.week_ending.desc()).limit(1))
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no postmortem")
    return PostmortemOut(
        week_ending=row.week_ending.isoformat(),
        swing_return_pct=row.swing_return_pct,
        nifty_return_pct=row.nifty_return_pct,
        regime_switched_return_pct=row.regime_switched_return_pct,
        random_baseline_return_pct=row.random_baseline_return_pct,
        n_swing_trades_closed=row.n_swing_trades_closed,
        drawdown_pct=row.drawdown_pct,
        report_md_path=row.report_md_path,
    )


@router.get("/cooldowns/{symbol}", response_model=list[CooldownRowOut])
def get_cooldowns(symbol: str, db: Session = Depends(get_db)) -> list[CooldownRowOut]:
    rows = (
        db.execute(
            select(AlertCooldown)
            .where(AlertCooldown.symbol == symbol)
            .order_by(AlertCooldown.kind, AlertCooldown.last_fired_at.desc())
        )
        .scalars()
        .all()
    )
    return [CooldownRowOut.model_validate(r, from_attributes=True) for r in rows]
