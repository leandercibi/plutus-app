from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from plutus.config.settings import Settings
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy
from plutus.shared.fills.types import OHLCBar, TradePlan

_policy = FillPolicy(SlippageModel(Settings(_env_file=None)))


@settings(derandomize=True, max_examples=100)
@given(
    days_ahead=st.integers(min_value=1, max_value=30),
    open_=st.decimals(min_value=Decimal("50"), max_value=Decimal("500"), places=2),
)
def test_entry_fill_is_strictly_after_signal_bar(
    days_ahead: int, open_: Decimal
) -> None:
    signal_day = date(2025, 1, 1)
    next_bar = OHLCBar(
        as_of=signal_day + timedelta(days=days_ahead),
        open=open_,
        high=open_ + Decimal("5"),
        low=open_ - Decimal("5"),
        close=open_,
    )
    plan = TradePlan(
        symbol="X",
        signal_date=signal_day,
        entry=open_,
        stop_loss=open_ - Decimal("10"),
        target_1=open_ + Decimal("10"),
        target_2=open_ + Decimal("20"),
    )
    fill = _policy.fill_entry(plan, next_bar, adv=1_000_000, atr_pct=0.02)
    signal_dt = datetime.combine(signal_day, datetime.min.time())
    assert fill.filled_at > signal_dt
