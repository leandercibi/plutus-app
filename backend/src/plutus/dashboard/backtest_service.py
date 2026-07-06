"""Run a single-symbol backtest from the dashboard.

Glue between the dashboard widget and `plutus.backtesting.runner.BacktestRunner`.
Single-symbol, single-bundle, walks every day in the requested window. Uses
yfinance for OHLCV and SIDEWAYS as the regime stand-in when the API isn't up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from plutus.backtesting.runner import BacktestConfig, BacktestResult, BacktestRunner
from plutus.config.settings import get_settings
from plutus.swing.bundles.base import BundleContext

SINGLE_BUNDLE_FACTORIES = {
    "trend": lambda s: _import_bundle("trend", "TrendBundle", s),
    "breakout": lambda s: _import_bundle("breakout", "BreakoutBundle", s),
    "reversal": lambda s: _import_bundle("reversal", "ReversalBundle", s),
    "vcp": lambda s: _import_bundle("vcp", "VCPBundle", s),
}

# Composite ensembles the four single bundles; spec A5 fixed geometry.
# PEAD (C2) and SMC (C3) are gated by spec and not exposed in the lab.
BUNDLE_FACTORIES = SINGLE_BUNDLE_FACTORIES | {"composite": None}


def _import_bundle(module: str, klass: str, settings):
    mod = __import__(f"plutus.swing.bundles.{module}", fromlist=[klass])
    return getattr(mod, klass)(settings)


class _StubCalibration:
    """Lab fallback — no live calibration data; flat 50% T1, 25% T2."""

    def hit_rate(self, bundle: str, regime: str, target_field: str) -> float:
        return 0.5 if target_field == "target_1" else 0.25

    def confidence_band(self, bundle: str, regime: str, score_bucket: str) -> str:
        return "low"

    def n_for(self, bundle: str, regime: str) -> int:
        return 0


@dataclass(frozen=True)
class BacktestSummary:
    bundle: str
    symbol: str
    start: date
    end: date
    n_trades: int
    win_rate: float
    expectancy_R: float
    sum_R: float
    avg_hold_days: float
    fills_before_signal: int
    cost_model_on: bool
    fill_policy_on: bool
    trades_df: pd.DataFrame


def run_single_symbol_backtest(
    bundle_name: str,
    symbol: str,
    lookback_days: int = 365,
    use_cost_model: bool = True,
    use_fill_policy: bool = True,
) -> BacktestSummary:
    """Fetch OHLCV, walk the window, return aggregated results."""
    settings = get_settings()
    if bundle_name not in BUNDLE_FACTORIES:
        raise ValueError(
            f"Bundle '{bundle_name}' not supported in the lab "
            f"(allowed: {sorted(BUNDLE_FACTORIES)}; pead/smc are gated by spec C2/C3)"
        )
    is_composite = bundle_name == "composite"
    sub_bundles = (
        {name: factory(settings) for name, factory in SINGLE_BUNDLE_FACTORIES.items()}
        if is_composite
        else {bundle_name: SINGLE_BUNDLE_FACTORIES[bundle_name](settings)}
    )

    # Fetch candles via the same provider the pipeline uses.
    from plutus.data.providers.delivery_stub import DeliveryStubProvider
    from plutus.data.providers.yfinance_provider import YFinanceProvider

    today = date.today()
    start = today - timedelta(days=lookback_days)
    provider = YFinanceProvider()
    try:
        df = provider.fetch(symbol, start, today)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"OHLCV fetch failed for {symbol}: {exc}") from exc
    if df is None or df.empty:
        raise RuntimeError(f"OHLCV empty for {symbol}")
    candles = df.copy()
    candles.columns = [c.lower() for c in candles.columns]
    if "date" not in candles.columns:
        candles = candles.reset_index()
        candles.rename(columns={candles.columns[0]: "date"}, inplace=True)
    candles["date"] = pd.to_datetime(candles["date"])
    candles = candles.sort_values("date").reset_index(drop=True)

    # ATR % over last 14 sessions (used by slippage model).
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    tr = (high - low).abs()
    atr = float(tr.rolling(14).mean().iloc[-1] / close.iloc[-1]) if len(candles) >= 14 else 0.02
    adv = int(candles["volume"].astype(float).tail(20).mean() or 1)

    def get_universe_at(_d: date) -> frozenset[str]:
        return frozenset({symbol})

    def candles_for(_sym: str) -> pd.DataFrame:
        return candles

    def regime_at(_d: date) -> str:
        return "SIDEWAYS"

    delivery_provider = DeliveryStubProvider()
    delivery_full = delivery_provider.annotate_delivery(symbol, candles)

    if is_composite:
        from plutus.swing.bundles.composite import CompositeBundle

        composite = CompositeBundle(_StubCalibration(), "SIDEWAYS")

    def fit_signal(sym: str, frame: pd.DataFrame, _d: date):
        delivery_slice = delivery_full.iloc[: len(frame)]
        if is_composite:
            sub_signals = []
            for sub in sub_bundles.values():
                ctx_sub = BundleContext(symbol=sym, regime="SIDEWAYS", delivery=delivery_slice)
                try:
                    sig = sub.fit_signal(sym, frame, ctx_sub)
                except Exception:  # noqa: BLE001
                    sig = None
                if sig is not None:
                    sub_signals.append(sig)
            if len(sub_signals) < 2:
                return None
            ctx_comp = BundleContext(
                symbol=sym,
                regime="SIDEWAYS",
                delivery=delivery_slice,
                extras={"sub_signals": sub_signals},
            )
            return composite.fit_signal(sym, frame, ctx_comp)
        sub = next(iter(sub_bundles.values()))
        ctx = BundleContext(symbol=sym, regime="SIDEWAYS", delivery=delivery_slice)
        return sub.fit_signal(sym, frame, ctx)

    cfg = BacktestConfig(
        start=start,
        end=today,
        bundles=[bundle_name],
        use_cost_model=use_cost_model,
        use_fill_policy=use_fill_policy,
    )
    runner = BacktestRunner(settings)
    res: BacktestResult = runner.run(
        cfg,
        get_universe_at,
        candles_for,
        regime_at,
        fit_signal,
        lambda _s: adv,
        lambda _s: atr,
    )

    trades = res.trades
    n = len(trades)
    win_rate = sum(1 for t in trades if t.realized_R > 0) / n if n else 0.0
    sum_r = sum(t.realized_R for t in trades) if trades else 0.0
    expectancy = sum_r / n if n else 0.0
    avg_hold = sum(t.hold_days for t in trades) / n if n else 0.0
    trades_df = pd.DataFrame(
        [
            {
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "hold_days": t.hold_days,
                "realized_R": round(t.realized_R, 3),
            }
            for t in trades
        ]
    )
    return BacktestSummary(
        bundle=bundle_name,
        symbol=symbol,
        start=start,
        end=today,
        n_trades=n,
        win_rate=win_rate,
        expectancy_R=expectancy,
        sum_R=sum_r,
        avg_hold_days=avg_hold,
        fills_before_signal=res.fills_before_signal,
        cost_model_on=use_cost_model,
        fill_policy_on=use_fill_policy,
        trades_df=trades_df,
    )
