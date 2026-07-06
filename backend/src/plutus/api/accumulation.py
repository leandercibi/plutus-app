from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.api.auth import require_token
from plutus.api.deps import get_db
from plutus.api.schemas.accumulation import (
    AccumulationCandidateOut,
    AccumulationPositionOut,
    ExitPositionIn,
    PauseIn,
    StartPositionIn,
    TrancheFilledIn,
    TrancheOut,
)
from plutus.api.schemas.swing import SwingTradeOut
from plutus.db.models import (
    AccumulationCandidate,
    AccumulationPosition,
    SwingSignal,
    SwingTrade,
    Tranche,
)

router = APIRouter(
    prefix="/accumulation", tags=["accumulation"], dependencies=[Depends(require_token)]
)


@router.get("/candidates", response_model=list[AccumulationCandidateOut])
def list_candidates(
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AccumulationCandidateOut]:
    stmt = select(AccumulationCandidate)
    if run_id is not None:
        stmt = stmt.where(AccumulationCandidate.run_id == run_id)
    stmt = stmt.order_by(AccumulationCandidate.created_at.desc(), AccumulationCandidate.id.desc())
    return [
        AccumulationCandidateOut.model_validate(r, from_attributes=True)
        for r in db.execute(stmt).scalars().all()
    ]


@router.get("/positions", response_model=list[AccumulationPositionOut])
def list_positions(db: Session = Depends(get_db)) -> list[AccumulationPositionOut]:
    rows = (
        db.execute(select(AccumulationPosition).order_by(AccumulationPosition.opened_at.desc()))
        .scalars()
        .all()
    )
    return [AccumulationPositionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/positions/{position_id}/tranches", response_model=list[TrancheOut])
def list_tranches(position_id: int, db: Session = Depends(get_db)) -> list[TrancheOut]:
    rows = (
        db.execute(select(Tranche).where(Tranche.position_id == position_id).order_by(Tranche.seq))
        .scalars()
        .all()
    )
    return [TrancheOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/positions", response_model=AccumulationPositionOut, status_code=201)
def start_position(body: StartPositionIn, db: Session = Depends(get_db)) -> AccumulationPositionOut:
    """Create a new accumulation position and log the first tranche buy."""
    existing = db.execute(
        select(AccumulationPosition).where(
            AccumulationPosition.symbol == body.symbol,
            AccumulationPosition.state.in_(["BUILDING", "FULL", "PAUSED"]),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="active position already exists for this symbol"
        )

    now = datetime.utcnow()
    pos = AccumulationPosition(
        symbol=body.symbol,
        state="BUILDING",
        avg_cost=body.price,
        qty_total=body.qty,
        opened_at=now,
        last_thesis_check_at=now,
    )
    db.add(pos)
    db.flush()  # get pos.id

    tranche = Tranche(
        position_id=pos.id,
        seq=1,
        qty=body.qty,
        atr_normalized_trigger_pct=0.0,
        filled_at_price=body.price,
        filled_at=now,
        thesis_revalidated=True,
    )
    db.add(tranche)
    db.flush()
    return AccumulationPositionOut.model_validate(pos, from_attributes=True)


@router.post("/positions/{position_id}/tranches", response_model=TrancheOut, status_code=201)
def log_tranche_fill(
    position_id: int, body: TrancheFilledIn, db: Session = Depends(get_db)
) -> TrancheOut:
    """Log the next tranche buy for an existing position, updating avg cost."""
    pos = db.get(AccumulationPosition, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    if pos.state in ("EXITED", "CONVERTED_TO_SWING"):
        raise HTTPException(status_code=409, detail="position is closed")

    existing_tranches = (
        db.execute(
            select(Tranche)
            .where(Tranche.position_id == position_id, Tranche.filled_at.isnot(None))
            .order_by(Tranche.seq)
        )
        .scalars()
        .all()
    )
    next_seq = len(existing_tranches) + 1
    if next_seq > 5:
        raise HTTPException(status_code=409, detail="all 5 tranches already filled")

    now = datetime.utcnow()

    # Weighted average cost update
    old_value = pos.avg_cost * pos.qty_total
    new_value = body.price * body.qty
    new_qty = pos.qty_total + body.qty
    pos.avg_cost = (old_value + new_value) / new_qty
    pos.qty_total = new_qty
    pos.state = "FULL" if next_seq == 5 else "BUILDING"

    tranche = Tranche(
        position_id=position_id,
        seq=next_seq,
        qty=body.qty,
        atr_normalized_trigger_pct=0.0,
        filled_at_price=body.price,
        filled_at=now,
        thesis_revalidated=True,
    )
    db.add(tranche)
    db.flush()
    return TrancheOut.model_validate(tranche, from_attributes=True)


@router.post("/positions/{position_id}/exit", response_model=AccumulationPositionOut)
def exit_position(
    position_id: int, body: ExitPositionIn, db: Session = Depends(get_db)
) -> AccumulationPositionOut:
    """Log a full exit of the position."""
    pos = db.get(AccumulationPosition, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    if pos.state in ("EXITED", "CONVERTED_TO_SWING"):
        raise HTTPException(status_code=409, detail="position already closed")
    pos.state = "EXITED"
    db.flush()
    return AccumulationPositionOut.model_validate(pos, from_attributes=True)


@router.post("/positions/{position_id}/pause", response_model=AccumulationPositionOut)
def pause_position(
    position_id: int, body: PauseIn, db: Session = Depends(get_db)
) -> AccumulationPositionOut:
    pos = db.get(AccumulationPosition, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    pos.state = "PAUSED"
    pos.paused_reason = body.reason
    db.flush()
    return AccumulationPositionOut.model_validate(pos, from_attributes=True)


@router.post("/positions/{position_id}/resume", response_model=AccumulationPositionOut)
def resume_position(position_id: int, db: Session = Depends(get_db)) -> AccumulationPositionOut:
    pos = db.get(AccumulationPosition, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    if pos.state != "PAUSED":
        raise HTTPException(status_code=409, detail="position is not paused")
    pos.state = "BUILDING"
    db.flush()
    return AccumulationPositionOut.model_validate(pos, from_attributes=True)


@router.post("/positions/{position_id}/convert-to-swing", response_model=SwingTradeOut)
def convert_to_swing(position_id: int, db: Session = Depends(get_db)) -> SwingTradeOut:
    pos = db.get(AccumulationPosition, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="position not found")
    if pos.state == "CONVERTED_TO_SWING":
        raise HTTPException(status_code=409, detail="already converted")

    now = datetime.utcnow()
    # Bull-ready conversion: average cost becomes the reporting entry; a fresh
    # swing plan sets stop/targets later. Seed a signal so the trade FK is valid.
    signal = SwingSignal(
        run_id=f"convert-{position_id}",
        symbol=pos.symbol,
        bundle="bull_ready",
        score=0,
        label="WATCH",
        entry=pos.avg_cost,
        stop_loss=pos.avg_cost,
        target_1=pos.avg_cost,
        target_2=pos.avg_cost,
        expectancy_R=0.0,
        drawn_rr=0.0,
        regime_at_signal="BULL",
        pillar_breakdown_json={},
        counterfactual_text=None,
        created_at=now,
    )
    db.add(signal)
    db.flush()

    trade = SwingTrade(
        signal_id=signal.id,
        symbol=pos.symbol,
        bundle="bull_ready",
        state="OPEN",
        opened_at=now,
        qty=pos.qty_total,
        risk_R=0.0,
    )
    db.add(trade)
    pos.state = "CONVERTED_TO_SWING"
    db.flush()
    return SwingTradeOut.model_validate(trade, from_attributes=True)
