# src/plutus/backtesting/runner.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

import backtrader as bt

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv, InsufficientDataError
from plutus.data.universe import get_universe
from plutus.db.session import SessionLocal
from plutus.db.models import BacktestResult, WeeklyRun
from plutus.strategies.bundle_trend import TrendBundle
from plutus.strategies.bundle_reversal import ReversalBundle
from plutus.strategies.bundle_breakout import BreakoutBundle
from plutus.strategies.bundle_smc import SMCBundle
from plutus.strategies.bundle_composite import CompositeBundle
from plutus.strategies.bundle_vcp import VCPBundle
from plutus.strategies.bundle_pead import PEADBundle


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------- #
# Result type
# ---------------------------------------------------------------------- #
MIN_BARS_REQUIRED = 60
SHARPE_SANE_MIN = -5.0
SHARPE_SANE_MAX = 5.0


@dataclass
class BundleResult:
    """Per-bundle, per-symbol backtest summary."""

    bundle_name: str
    win_rate: float  # 0.0 – 1.0
    avg_return_pct: float  # arithmetic mean of trade % returns
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    trades: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suspect: bool = False


BUNDLE_MAP: Dict[str, type] = {
    "trend": TrendBundle,
    "reversal": ReversalBundle,
    "breakout": BreakoutBundle,
    "smc": SMCBundle,
    "composite": CompositeBundle,
    "vcp": VCPBundle,
    "pead": PEADBundle,
}


# ---------------------------------------------------------------------- #
# Single-bundle runner
# ---------------------------------------------------------------------- #
def run_bundle(symbol: str, bundle_name: str, days: int = 90) -> BundleResult:
    """Run one bundle on `symbol` for `days` of daily OHLCV. Returns a BundleResult."""
    if bundle_name not in BUNDLE_MAP:
        raise ValueError(f"Unknown bundle: {bundle_name}")

    try:
        df = fetch_ohlcv(symbol, days=days, interval="1d")
        bars = len(df) if df is not None else 0

        if bars < MIN_BARS_REQUIRED:
            raise InsufficientDataError(bars, MIN_BARS_REQUIRED, symbol)

        warnings: List[str] = []
        if bars < days:
            warnings.append(
                f"Only {bars}/{days} bars available — results may be less reliable"
            )

        engine = bt.Cerebro(stdstats=False)
        engine.addstrategy(BUNDLE_MAP[bundle_name])
        engine.broker.setcash(settings.INITIAL_CAPITAL)
        engine.broker.setcommission(commission=0.001)  # 0.1% per side, NSE-realistic

        engine.adddata(bt.feeds.PandasData(dataname=df))
        engine.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        engine.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

        results = engine.run()
        strat = results[0]
        result = _summarise(bundle_name, strat)
        result.warnings.extend(warnings)
        return result
    except InsufficientDataError:
        raise
    except Exception:
        log.exception("run_bundle failed: symbol=%s bundle=%s", symbol, bundle_name)
        return _empty_result(bundle_name)


def _summarise(bundle_name: str, strat) -> BundleResult:
    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()

    closed = ta.get("total", {}).get("closed", 0) or 0
    won = ta.get("won", {}).get("total", 0) or 0
    win_rate = (won / closed) if closed > 0 else 0.0

    trades = list(getattr(strat, "trade_log", []) or [])
    if trades:
        avg_return = sum(t.get("pnl_pct", 0.0) for t in trades) / len(trades)
    else:
        avg_return = 0.0

    max_dd = (dd.get("max", {}).get("drawdown", 0.0)) or 0.0

    if trades and len(trades) >= 2:
        returns = [t.get("pnl_pct", 0.0) for t in trades]
        avg_ret = sum(returns) / len(returns)
        std_ret = (sum((r - avg_ret) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe_val = (avg_ret / std_ret) if std_ret > 0 else 0.0
    elif trades and len(trades) == 1:
        sharpe_val = 1.0 if trades[0].get("pnl_pct", 0) > 0 else -1.0
    else:
        sharpe_val = 0.0

    suspect = not (SHARPE_SANE_MIN <= sharpe_val <= SHARPE_SANE_MAX)
    sharpe_val = max(SHARPE_SANE_MIN, min(SHARPE_SANE_MAX, sharpe_val))

    result_warnings: List[str] = []
    if suspect:
        result_warnings.append(
            f"Sharpe {round(sharpe_val, 3)} outside sane range [{SHARPE_SANE_MIN}, {SHARPE_SANE_MAX}] — flagged as suspect"
        )
    if closed == 0:
        result_warnings.append("No trades generated — strategy produced no signals")

    return BundleResult(
        bundle_name=bundle_name,
        win_rate=round(win_rate, 3),
        avg_return_pct=round(avg_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe_val, 3),
        total_trades=closed,
        trades=trades,
        warnings=result_warnings,
        suspect=suspect,
    )


def _empty_result(bundle_name: str) -> BundleResult:
    return BundleResult(
        bundle_name=bundle_name,
        win_rate=0.0,
        avg_return_pct=0.0,
        max_drawdown_pct=0.0,
        sharpe_ratio=0.0,
        total_trades=0,
        trades=[],
    )


# ---------------------------------------------------------------------- #
# 5-bundle batch runner
# ---------------------------------------------------------------------- #
def run_all_bundles(symbol: str, days: int = 90) -> Dict[str, BundleResult]:
    """Run all registered bundles on a symbol. Returns a dict keyed by bundle name."""
    return {name: run_bundle(symbol, name, days=days) for name in BUNDLE_MAP}


def select_best_bundles(results: Dict[str, BundleResult]) -> List[str]:
    """Top 2 bundle names by Sharpe from the provided results dict.

    Bundles with `total_trades == 0` are demoted (treated as Sharpe = -inf) so
    we never pick a bundle that did not actually trade in the window.
    """

    def key(name: str) -> float:
        r = results[name]
        if r.total_trades <= 0:
            return float("-inf")
        return r.sharpe_ratio

    ordered = sorted(results.keys(), key=key, reverse=True)
    return ordered[:2]


# ---------------------------------------------------------------------- #
# Weekly pipeline
# ---------------------------------------------------------------------- #
TOP_N_CANDIDATES = 20


def weekly_pipeline(weekly_run_id: int, days: int = 90) -> List[str]:
    """Rank every universe symbol by best-bundle Sharpe; return top 20 symbols.

    Side effects: writes one `backtest_results` row per (symbol, bundle) for
    the given `weekly_run_id`.
    """
    universe = get_universe()
    log.info("weekly_pipeline: %d symbols", len(universe))

    ranked: List[tuple[str, float, Dict[str, BundleResult]]] = []
    for symbol in universe:
        results = run_all_bundles(symbol, days=days)
        save_backtest_results(weekly_run_id, symbol, results)

        best_sharpe = max(
            (r.sharpe_ratio for r in results.values() if r.total_trades > 0),
            default=float("-inf"),
        )
        ranked.append((symbol, best_sharpe, results))

    ranked.sort(key=lambda x: x[1], reverse=True)
    top = [
        sym for sym, sharpe, _ in ranked[:TOP_N_CANDIDATES] if sharpe > float("-inf")
    ]
    log.info("weekly_pipeline: top %d → %s", len(top), top)
    return top


# ---------------------------------------------------------------------- #
# Persistence
# ---------------------------------------------------------------------- #
def save_backtest_results(
    weekly_run_id: int,
    symbol: str,
    results: Dict[str, BundleResult],
) -> None:
    """Persist one row per bundle for this symbol's run."""
    today = date.today()
    with SessionLocal() as db:
        for bundle_name, r in results.items():
            db.add(
                BacktestResult(
                    weekly_run_id=weekly_run_id,
                    symbol=symbol,
                    run_date=today,
                    bundle_name=bundle_name,
                    win_rate=r.win_rate,
                    avg_return_pct=r.avg_return_pct,
                    max_drawdown_pct=r.max_drawdown_pct,
                    sharpe_ratio=r.sharpe_ratio,
                    total_trades=r.total_trades,
                )
            )
        db.commit()
