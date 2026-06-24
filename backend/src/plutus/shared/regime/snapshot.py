from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from plutus.db.models import RegimeSnapshot
from plutus.shared.regime.detector import RegimeInputs, RegimeVerdict


def save_snapshot(
    as_of: date,
    verdict: RegimeVerdict,
    inputs: RegimeInputs,
    session: Session,
) -> RegimeSnapshot:
    row = RegimeSnapshot(
        as_of_date=as_of,
        label=verdict.label,
        nifty_close=inputs.nifty_close,
        pct_above_50dma=inputs.pct_above_50dma,
        pct_above_200dma=inputs.pct_above_200dma,
        advance_decline=inputs.advance_decline,
        india_vix=inputs.india_vix,
        fii_flow_inr=inputs.fii_flow_5d_sum_inr,
        dii_flow_inr=inputs.dii_flow_5d_sum_inr,
        breadth_confirmed_flip=verdict.breadth_confirmed,
    )
    session.merge(row)
    return row


def read_snapshot(as_of: date, session: Session) -> RegimeSnapshot | None:
    return session.get(RegimeSnapshot, as_of)
