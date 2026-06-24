from __future__ import annotations

import statistics
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from plutus.backtesting.pooled import stats_from_trades
from plutus.shared.types import BacktestTrade, BundleStats


@dataclass(frozen=True)
class Window:
    start: date
    end: date


class WalkForward:
    def windows(
        self,
        start: date,
        end: date,
        train_days: int = 180,
        oos_days: int = 30,
        step_days: int = 30,
    ) -> Iterator[tuple[Window, Window]]:
        train_start = start
        while True:
            train_end = train_start + timedelta(days=train_days)
            oos_start = train_end
            oos_end = oos_start + timedelta(days=oos_days)
            if oos_end > end:
                break
            yield Window(train_start, train_end), Window(oos_start, oos_end)
            train_start = train_start + timedelta(days=step_days)

    def stats(self, trades: list[BacktestTrade], window: Window) -> BundleStats:
        in_window = [t for t in trades if window.start <= t.entry_date < window.end]
        bundle = in_window[0].bundle if in_window else "ALL"
        return stats_from_trades(in_window, bundle=bundle, regime="ALL")


# ---------------------------------------------------------------------------
# Phase 4B — bar-level walk-forward
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WFWindowResult:
    is_sharpe: float
    oos_sharpe: float
    is_trades: int
    oos_trades: int


@dataclass(frozen=True)
class WalkForwardReport:
    symbol: str
    bundle: str
    windows: list[WFWindowResult]
    is_sharpe_median: float
    oos_sharpe_median: float
    overfit_flag: bool


def split_walk_forward(
    bars: pd.DataFrame,
    window_days: int = 30,
    step_days: int = 7,
) -> Generator[dict[str, pd.DataFrame], None, None]:
    """Slide a fixed-size window over bars, yielding IS/OOS sub-frames.

    IS = first 70% of window_days bars; OOS = remaining 30%.
    Windows advance by step_days bars each iteration.
    """
    is_size = int(window_days * 0.7)
    total = len(bars)
    start = 0
    while start + window_days <= total:
        w = bars.iloc[start : start + window_days]
        yield {"is_bars": w.iloc[:is_size], "oos_bars": w.iloc[is_size:]}
        start += step_days


_SUPPORTED_BUNDLES = {"trend", "breakout", "vcp", "reversal"}


def walk_forward(
    symbol: str,
    bundle: str,
    window_days: int = 30,
    step_days: int = 7,
    lookback_days: int = 730,
) -> WalkForwardReport:
    """Run IS/OOS walk-forward for one (symbol, bundle) pair.

    Fetches OHLCV once from yfinance, then runs BacktestRunner over each IS
    and OOS date range in turn. Computes per-window Sharpe and flags overfit
    when OOS Sharpe drops > 50 % vs IS in ≥ 50 % of windows.
    """
    if bundle not in _SUPPORTED_BUNDLES:
        raise ValueError(f"bundle '{bundle}' not supported; choose from {sorted(_SUPPORTED_BUNDLES)}")

    from plutus.backtesting.runner import BacktestConfig, BacktestRunner
    from plutus.config.settings import get_settings
    from plutus.data.providers.delivery_stub import DeliveryStubProvider
    from plutus.data.providers.yfinance_provider import YFinanceProvider
    from plutus.swing.bundles.base import BundleContext

    settings = get_settings()
    today = date.today()
    start_date = today - timedelta(days=lookback_days)

    provider = YFinanceProvider()
    df = provider.fetch(symbol, start_date, today)
    if df is None or df.empty:
        raise RuntimeError(f"OHLCV empty for {symbol}")

    candles = df.copy()
    candles.columns = [c.lower() for c in candles.columns]
    if "date" not in candles.columns:
        candles = candles.reset_index()
        candles.rename(columns={candles.columns[0]: "date"}, inplace=True)
    candles["date"] = pd.to_datetime(candles["date"])
    candles = candles.sort_values("date").reset_index(drop=True)

    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    tr = (high - low).abs()
    atr = float(tr.rolling(14).mean().iloc[-1] / close.iloc[-1]) if len(candles) >= 14 else 0.02
    adv = int(candles["volume"].astype(float).tail(20).mean() or 1)

    klass_name = "".join(p.title() for p in bundle.split("_")) + "Bundle"
    mod = __import__(f"plutus.swing.bundles.{bundle}", fromlist=[klass_name])
    bundle_obj = getattr(mod, klass_name)(settings)
    delivery_full = DeliveryStubProvider().annotate_delivery(symbol, candles)

    def _fit(sym: str, frame: pd.DataFrame, _d: date):
        delivery_slice = delivery_full.iloc[: len(frame)]
        ctx = BundleContext(symbol=sym, regime="SIDEWAYS", delivery=delivery_slice)
        return bundle_obj.fit_signal(sym, frame, ctx)

    runner = BacktestRunner(settings)
    results: list[WFWindowResult] = []

    for split in split_walk_forward(candles, window_days, step_days):
        is_bars = split["is_bars"]
        oos_bars = split["oos_bars"]
        if is_bars.empty or oos_bars.empty:
            continue

        def _run(cfg_start: date, cfg_end: date) -> list[BacktestTrade]:
            cfg = BacktestConfig(start=cfg_start, end=cfg_end, bundles=[bundle])
            res = runner.run(
                cfg,
                lambda _d: frozenset({symbol}),
                lambda _s: candles,
                lambda _d: "SIDEWAYS",
                _fit,
                lambda _s: adv,
                lambda _s: atr,
            )
            return res.trades

        is_start = is_bars["date"].iloc[0].date()
        is_end = is_bars["date"].iloc[-1].date()
        oos_start = oos_bars["date"].iloc[0].date()
        oos_end = oos_bars["date"].iloc[-1].date()

        is_stats = stats_from_trades(_run(is_start, is_end), bundle, "ALL")
        oos_stats = stats_from_trades(_run(oos_start, oos_end), bundle, "ALL")
        results.append(
            WFWindowResult(
                is_sharpe=is_stats.sharpe_raw,
                oos_sharpe=oos_stats.sharpe_raw,
                is_trades=is_stats.n_trades,
                oos_trades=oos_stats.n_trades,
            )
        )

    if not results:
        return WalkForwardReport(
            symbol=symbol,
            bundle=bundle,
            windows=[],
            is_sharpe_median=0.0,
            oos_sharpe_median=0.0,
            overfit_flag=False,
        )

    is_med = statistics.median(w.is_sharpe for w in results)
    oos_med = statistics.median(w.oos_sharpe for w in results)
    n_overfit = sum(
        1
        for w in results
        if w.is_sharpe > 0 and (w.is_sharpe - w.oos_sharpe) / w.is_sharpe > 0.5
    )
    overfit_flag = n_overfit / len(results) >= 0.5

    return WalkForwardReport(
        symbol=symbol,
        bundle=bundle,
        windows=results,
        is_sharpe_median=is_med,
        oos_sharpe_median=oos_med,
        overfit_flag=overfit_flag,
    )


# ---------------------------------------------------------------------------
# CLI (Task 4b.4): python -m plutus.backtesting.walk_forward --symbol ...
# ---------------------------------------------------------------------------

try:
    import click

    @click.command()
    @click.option("--symbol", required=True, help="NSE symbol (e.g. RELIANCE)")
    @click.option(
        "--bundle",
        required=True,
        type=click.Choice(sorted(_SUPPORTED_BUNDLES)),
        help="Bundle name",
    )
    @click.option("--window", "window_days", default=30, show_default=True, help="Window size (bars)")
    @click.option("--step", "step_days", default=7, show_default=True, help="Step size (bars)")
    @click.option("--lookback", "lookback_days", default=730, show_default=True, help="Lookback days")
    def cli(symbol: str, bundle: str, window_days: int, step_days: int, lookback_days: int) -> None:
        """Run IS/OOS walk-forward for a single symbol + bundle."""
        report = walk_forward(symbol, bundle, window_days, step_days, lookback_days)
        click.echo(f"Walk-Forward: {report.symbol} · {report.bundle}")
        click.echo(f"  Windows:           {len(report.windows)}")
        click.echo(f"  IS Sharpe median:  {report.is_sharpe_median:.3f}")
        click.echo(f"  OOS Sharpe median: {report.oos_sharpe_median:.3f}")
        click.echo(f"  Overfit flag:      {'YES ⚠' if report.overfit_flag else 'no'}")
        if report.windows:
            click.echo("\n  Window detail (IS → OOS):")
            for i, w in enumerate(report.windows, 1):
                click.echo(
                    f"    [{i:2d}] IS {w.is_sharpe:+.3f} (n={w.is_trades:3d}) "
                    f"OOS {w.oos_sharpe:+.3f} (n={w.oos_trades:3d})"
                )

    if __name__ == "__main__":
        cli()

except ImportError:
    pass
