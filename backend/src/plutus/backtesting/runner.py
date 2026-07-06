from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import pandas as pd

from plutus.config.settings import Settings
from plutus.shared.cost_model.costs import CostModel
from plutus.shared.cost_model.slippage import SlippageModel
from plutus.shared.fills.policy import FillPolicy
from plutus.shared.fills.types import OHLCBar, TradePlan
from plutus.shared.types import BacktestTrade, BundleSignal


@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    bundles: list[str]
    universe_source: Literal["pit"] = "pit"
    use_cost_model: bool = True
    use_fill_policy: bool = True


@dataclass(frozen=True)
class OpenTrade:
    signal: BundleSignal
    plan: TradePlan
    entry_price: Decimal
    entry_date: date
    qty: int


@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade]
    config: BacktestConfig
    fills_before_signal: int = 0


# A1 CI guard: the runner must use a PIT universe accessor, never a live one.
FitFn = Callable[[str, pd.DataFrame, date], BundleSignal | None]
UniverseAt = Callable[[date], frozenset[str]]
CandlesFor = Callable[[str], pd.DataFrame]


class BacktestRunner:
    """A1 — signals on bar T can only execute on bar T+1, via FillPolicy."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        slippage = SlippageModel(settings)
        self._fills = FillPolicy(slippage)
        self._costs = CostModel(settings)

    def run(
        self,
        cfg: BacktestConfig,
        get_universe_at: UniverseAt,
        candles_for: CandlesFor,
        regime_at: Callable[[date], str],
        fit_signal: FitFn,
        adv_for: Callable[[str], int],
        atr_pct_for: Callable[[str], float],
    ) -> BacktestResult:
        trades: list[BacktestTrade] = []
        lookahead_violations = 0

        day = cfg.start
        while day <= cfg.end:
            for symbol in sorted(get_universe_at(day)):
                candles = candles_for(symbol)
                upto = candles[candles["date"] <= pd.Timestamp(day)]
                if upto.empty:
                    continue
                signal = fit_signal(symbol, upto, day)
                if signal is None:
                    continue

                next_bar = self._next_bar(candles, day)
                if next_bar is None:
                    continue
                if next_bar.as_of <= day:
                    lookahead_violations += 1
                    continue

                plan = TradePlan(
                    symbol=symbol,
                    signal_date=day,
                    entry=signal.entry,
                    stop_loss=signal.stop_loss,
                    target_1=signal.target_1,
                    target_2=signal.target_2,
                )
                fill = self._fills.fill_entry(plan, next_bar, adv_for(symbol), atr_pct_for(symbol))
                trade = self._simulate(
                    signal,
                    plan,
                    fill.price,
                    next_bar.as_of,
                    candles,
                    regime_at(day),
                    adv_for(symbol),
                    atr_pct_for(symbol),
                    cfg,
                )
                if trade is not None:
                    trades.append(trade)
            day += timedelta(days=1)

        return BacktestResult(trades=trades, config=cfg, fills_before_signal=lookahead_violations)

    def _next_bar(self, candles: pd.DataFrame, day: date) -> OHLCBar | None:
        future = candles[candles["date"] > pd.Timestamp(day)]
        if future.empty:
            return None
        row = future.iloc[0]
        return OHLCBar(
            as_of=row["date"].date(),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
        )

    def _simulate(
        self,
        signal: BundleSignal,
        plan: TradePlan,
        entry_price: Decimal,
        entry_date: date,
        candles: pd.DataFrame,
        regime: str,
        adv: int,
        atr_pct: float,
        cfg: BacktestConfig,
    ) -> BacktestTrade | None:
        risk_per_share = entry_price - signal.stop_loss
        if risk_per_share <= 0:
            return None
        forward = candles[candles["date"] > pd.Timestamp(entry_date)]
        exit_price = entry_price
        exit_date = entry_date
        hold_days = 0
        for _, row in forward.iterrows():
            bar = OHLCBar(
                as_of=row["date"].date(),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
            )
            hold_days += 1
            stop_fill = self._fills.fill_stop(plan, bar, adv, atr_pct)
            if stop_fill is not None:
                exit_price, exit_date = stop_fill.price, bar.as_of
                break
            target_fill = self._fills.fill_target(plan, bar, 1, adv, atr_pct)
            if target_fill is not None:
                exit_price, exit_date = target_fill.price, bar.as_of
                break
            exit_price, exit_date = bar.close, bar.as_of

        gross_r = float((exit_price - entry_price) / risk_per_share)
        if cfg.use_cost_model:
            qty = 1
            cost = self._costs.round_trip_cost(qty, entry_price, exit_price)
            cost_r = float(cost / (risk_per_share * Decimal(qty)))
            realized_r = gross_r - cost_r
        else:
            realized_r = gross_r

        return BacktestTrade(
            symbol=signal.symbol,
            bundle=signal.bundle,
            regime=regime,
            entry_date=entry_date,
            exit_date=exit_date,
            realized_R=realized_r,
            hold_days=hold_days,
        )
