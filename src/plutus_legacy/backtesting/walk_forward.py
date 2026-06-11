"""
walk_forward.py — Rolling IS/OOS walk-forward evaluation.

Usage (CLI):
    python -m plutus.backtesting.walk_forward \\
        --symbol RELIANCE --bundle trend --window 60 --step 7 --oos 30

Algorithm:
  1. Fetch full OHLCV for symbol (window + n_steps * step + oos days).
  2. Slide a window forward in steps of `step` bars.
     IS  = [pos, pos + window_bars]
     OOS = [pos + window_bars, pos + window_bars + oos_bars]
  3. Run Backtrader on IS and OOS slices independently.
  4. Record IS Sharpe, OOS Sharpe, trade counts.
  5. Flag overfit when OOS Sharpe drops >50% from IS.
  6. Persist each row to walk_forward_runs table; also print a summary table.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import List, Optional

import backtrader as bt
import pandas as pd

from plutus.backtesting.runner import (
    BUNDLE_MAP,
    _summarise,
    _empty_result,
    BundleResult,
)
from plutus.data.ohlcv import fetch_ohlcv, InsufficientDataError

log = logging.getLogger(__name__)

MIN_IS_BARS = 60  # minimum bars for a valid IS window (EMA50 warmup ≈ 50+ADX)
MIN_OOS_BARS = 60  # minimum bars for a valid OOS slice (same warmup applies)
OVERFIT_THRESHOLD = 0.5  # OOS Sharpe < IS_Sharpe * (1 - this) → overfit

_COMMISSION = 0.001  # 0.1% per side, NSE-realistic


@dataclass
class WindowResult:
    window_idx: int
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date
    is_sharpe: float
    oos_sharpe: float
    is_trades: int
    oos_trades: int
    is_win_rate: float
    oos_win_rate: float
    overfit_flag: bool


@dataclass
class WalkForwardSummary:
    symbol: str
    bundle_name: str
    windows: List[WindowResult]
    mean_is_sharpe: float
    mean_oos_sharpe: float
    overfit_window_count: int
    overfit_pct: float  # % of windows flagged as overfit
    verdict: str  # "ROBUST" | "SUSPECT" | "OVERFIT"


def _run_on_slice(df_slice: pd.DataFrame, bundle_name: str) -> BundleResult:
    """Run one bundle strategy on a DataFrame slice. Returns BundleResult."""
    if len(df_slice) < MIN_IS_BARS:
        return _empty_result(bundle_name)
    cls = BUNDLE_MAP[bundle_name]
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(cls)
    cerebro.broker.setcash(100_000)
    cerebro.broker.setcommission(commission=_COMMISSION)
    cerebro.adddata(bt.feeds.PandasData(dataname=df_slice))
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    try:
        results = cerebro.run()
        if not results:
            return _empty_result(bundle_name)
        return _summarise(bundle_name, results[0])
    except Exception:
        return _empty_result(bundle_name)


def _overfit(is_sharpe: float, oos_sharpe: float) -> bool:
    """True when OOS Sharpe drops >50% relative to IS Sharpe (IS > 0)."""
    if is_sharpe <= 0:
        return False
    return oos_sharpe < is_sharpe * (1 - OVERFIT_THRESHOLD)


def run_walk_forward(
    symbol: str,
    bundle_name: str,
    *,
    window_bars: int = 60,
    step_bars: int = 7,
    oos_bars: int = 30,
    fetch_days: Optional[int] = None,
    df: Optional[pd.DataFrame] = None,
) -> WalkForwardSummary:
    """
    Run walk-forward evaluation on `symbol` / `bundle_name`.

    Either supply a pre-fetched `df` (for testing) or let the function
    fetch OHLCV for `fetch_days` (defaults to window + 4*step + oos).

    Returns a WalkForwardSummary with per-window results.
    """
    if bundle_name not in BUNDLE_MAP:
        raise ValueError(f"Unknown bundle '{bundle_name}'. Valid: {list(BUNDLE_MAP)}")

    if df is None:
        total_days = fetch_days or (window_bars + 4 * step_bars + oos_bars + 30)
        df = fetch_ohlcv(symbol, days=total_days, interval="1d")
        if df is None or len(df) < window_bars + oos_bars:
            raise InsufficientDataError(
                len(df) if df is not None else 0,
                window_bars + oos_bars,
                symbol,
            )

    total_bars = len(df)
    windows: List[WindowResult] = []

    pos = 0
    idx = 0
    while pos + window_bars + oos_bars <= total_bars:
        is_df = df.iloc[pos : pos + window_bars]
        oos_df = df.iloc[pos + window_bars : pos + window_bars + oos_bars]

        if len(is_df) < MIN_IS_BARS or len(oos_df) < MIN_OOS_BARS:
            break

        try:
            is_result = _run_on_slice(is_df, bundle_name)
            oos_result = _run_on_slice(oos_df, bundle_name)
        except Exception as exc:
            log.warning("walk_forward window %d failed: %s", idx, exc)
            pos += step_bars
            idx += 1
            continue

        overfit = _overfit(is_result.sharpe_ratio, oos_result.sharpe_ratio)

        windows.append(
            WindowResult(
                window_idx=idx,
                is_start=df.index[pos].date(),
                is_end=df.index[pos + window_bars - 1].date(),
                oos_start=df.index[pos + window_bars].date(),
                oos_end=df.index[pos + window_bars + oos_bars - 1].date(),
                is_sharpe=is_result.sharpe_ratio,
                oos_sharpe=oos_result.sharpe_ratio,
                is_trades=is_result.total_trades,
                oos_trades=oos_result.total_trades,
                is_win_rate=is_result.win_rate,
                oos_win_rate=oos_result.win_rate,
                overfit_flag=overfit,
            )
        )
        pos += step_bars
        idx += 1

    if not windows:
        return WalkForwardSummary(
            symbol=symbol,
            bundle_name=bundle_name,
            windows=[],
            mean_is_sharpe=0.0,
            mean_oos_sharpe=0.0,
            overfit_window_count=0,
            overfit_pct=0.0,
            verdict="NO_DATA",
        )

    mean_is = sum(w.is_sharpe for w in windows) / len(windows)
    mean_oos = sum(w.oos_sharpe for w in windows) / len(windows)
    n_overfit = sum(1 for w in windows if w.overfit_flag)
    overfit_pct = n_overfit / len(windows) * 100

    if overfit_pct >= 50:
        verdict = "OVERFIT"
    elif overfit_pct >= 25 or mean_oos < 0:
        verdict = "SUSPECT"
    else:
        verdict = "ROBUST"

    return WalkForwardSummary(
        symbol=symbol,
        bundle_name=bundle_name,
        windows=windows,
        mean_is_sharpe=round(mean_is, 3),
        mean_oos_sharpe=round(mean_oos, 3),
        overfit_window_count=n_overfit,
        overfit_pct=round(overfit_pct, 1),
        verdict=verdict,
    )


def persist_walk_forward(summary: WalkForwardSummary, db_session=None) -> None:
    """Write WalkForwardRun rows for each window in `summary`."""
    from plutus.db.models import WalkForwardRun
    from plutus.db.session import SessionLocal

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    try:
        today = date.today()
        for w in summary.windows:
            row = WalkForwardRun(
                symbol=summary.symbol,
                bundle_name=summary.bundle_name,
                run_date=today,
                window_idx=w.window_idx,
                is_start=w.is_start,
                is_end=w.is_end,
                oos_start=w.oos_start,
                oos_end=w.oos_end,
                is_sharpe=w.is_sharpe,
                oos_sharpe=w.oos_sharpe,
                is_trades=w.is_trades,
                oos_trades=w.oos_trades,
                is_win_rate=w.is_win_rate,
                oos_win_rate=w.oos_win_rate,
                overfit_flag=w.overfit_flag,
            )
            ctx.add(row)
        ctx.commit()
    finally:
        if close_ctx:
            ctx.close()


def _print_summary(summary: WalkForwardSummary) -> None:
    print(f"\n{'='*60}")
    print(f"Walk-Forward: {summary.symbol} / {summary.bundle_name}")
    print(f"{'='*60}")
    print(
        f"{'Win':>4}  {'IS Start':>10}  {'IS End':>10}  {'OOS Start':>10}  "
        f"{'IS Sh':>7}  {'OOS Sh':>7}  {'IS Tr':>6}  {'OOS Tr':>6}  {'Flag':>6}"
    )
    print("-" * 80)
    for w in summary.windows:
        flag = "OVERFIT" if w.overfit_flag else "ok"
        print(
            f"{w.window_idx:>4}  {str(w.is_start):>10}  {str(w.is_end):>10}  "
            f"{str(w.oos_start):>10}  {w.is_sharpe:>7.3f}  {w.oos_sharpe:>7.3f}  "
            f"{w.is_trades:>6}  {w.oos_trades:>6}  {flag:>7}"
        )
    print("-" * 80)
    print(f"Mean IS Sharpe:   {summary.mean_is_sharpe:.3f}")
    print(f"Mean OOS Sharpe:  {summary.mean_oos_sharpe:.3f}")
    print(
        f"Overfit windows:  {summary.overfit_window_count}/{len(summary.windows)} "
        f"({summary.overfit_pct:.1f}%)"
    )
    print(f"Verdict:          {summary.verdict}")
    print()


# ── CLI entry point ────────────────────────────────────────────────────────────


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest for a bundle/symbol."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bundle", required=True, choices=list(BUNDLE_MAP))
    parser.add_argument(
        "--window", type=int, default=60, help="IS window in trading days (default 60)"
    )
    parser.add_argument(
        "--step", type=int, default=7, help="Roll step in trading days (default 7)"
    )
    parser.add_argument(
        "--oos", type=int, default=30, help="OOS window in trading days (default 30)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Total OHLCV days to fetch (auto if omitted)",
    )
    parser.add_argument("--save", action="store_true", help="Persist results to DB")
    parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of table"
    )
    args = parser.parse_args()

    summary = run_walk_forward(
        symbol=args.symbol,
        bundle_name=args.bundle,
        window_bars=args.window,
        step_bars=args.step,
        oos_bars=args.oos,
        fetch_days=args.days,
    )

    if args.json:
        data = {
            "symbol": summary.symbol,
            "bundle_name": summary.bundle_name,
            "mean_is_sharpe": summary.mean_is_sharpe,
            "mean_oos_sharpe": summary.mean_oos_sharpe,
            "overfit_pct": summary.overfit_pct,
            "verdict": summary.verdict,
            "windows": [asdict(w) for w in summary.windows],
        }
        print(json.dumps(data, default=str, indent=2))
    else:
        _print_summary(summary)

    if args.save:
        persist_walk_forward(summary)
        print(f"Saved {len(summary.windows)} window rows to walk_forward_runs table.")


if __name__ == "__main__":
    _cli()
