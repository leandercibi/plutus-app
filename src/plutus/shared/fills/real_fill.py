from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.db.models import Fill


@dataclass(frozen=True)
class SlippageDivergenceReport:
    n_pairs: int
    mean_bps: float
    median_bps: float
    p90_bps: float


def log_real_fill(
    trade_id: int,
    side: Literal["BUY", "SELL"],
    qty: int,
    price: Decimal,
    filled_at: datetime,
    cost_inr: Decimal,
    session: Session,
) -> Fill:
    """B10. Persist a user-logged real broker fill; any mock fill is preserved."""
    fill = Fill(
        trade_id=trade_id,
        kind="REAL",
        side=side,
        qty=qty,
        price=price,
        cost_inr=cost_inr,
        slippage_bps=None,
        filled_at=filled_at,
    )
    session.add(fill)
    session.flush()
    return fill


def slippage_divergence_report(
    window: timedelta, session: Session, now: datetime | None = None
) -> SlippageDivergenceReport:
    """For trades with BOTH mock and real fills inside the window, report bps divergence."""
    cutoff = (now or datetime.utcnow()) - window
    rows = session.execute(select(Fill).where(Fill.filled_at >= cutoff)).scalars().all()

    by_trade: dict[int, dict[str, Fill]] = {}
    for f in rows:
        by_trade.setdefault(f.trade_id, {})[f.kind] = f

    diffs_bps: list[float] = []
    for fills in by_trade.values():
        if "MOCK" in fills and "REAL" in fills:
            mock, real = fills["MOCK"], fills["REAL"]
            if mock.price == 0:
                continue
            bps = float((real.price - mock.price) / mock.price) * 10_000
            diffs_bps.append(bps)

    if not diffs_bps:
        return SlippageDivergenceReport(0, 0.0, 0.0, 0.0)

    diffs_bps.sort()
    p90_idx = min(len(diffs_bps) - 1, int(round(0.9 * (len(diffs_bps) - 1))))
    return SlippageDivergenceReport(
        n_pairs=len(diffs_bps),
        mean_bps=statistics.mean(diffs_bps),
        median_bps=statistics.median(diffs_bps),
        p90_bps=diffs_bps[p90_idx],
    )
