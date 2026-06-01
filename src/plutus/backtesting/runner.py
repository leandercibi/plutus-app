# src/plutus/backtesting/runner.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

import backtrader as bt

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv
from plutus.data.universe import get_universe
from plutus.db.session import SessionLocal
from plutus.db.models import BacktestResult, WeeklyRun
from plutus.strategies.bundle_trend import TrendBundle
from plutus.strategies.bundle_reversal import ReversalBundle
from plutus.strategies.bundle_breakout import BreakoutBundle
from plutus.strategies.bundle_smc import SMCBundle
from plutus.strategies.bundle_composite import CompositeBundle


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------- #
# Result type
# ---------------------------------------------------------------------- #
@dataclass
class BundleResult:
    """Per-bundle, per-symbol backtest summary."""
    bundle_name: str
    win_rate: float                       # 0.0 – 1.0
    avg_return_pct: float                 # arithmetic mean of trade % returns
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    trades: List[Dict] = field(default_factory=list)   # raw trade dicts from BaseStrategy.trade_log


BUNDLE_MAP: Dict[str, type] = {
    "trend":     TrendBundle,
    "reversal":  ReversalBundle,
    "breakout":  BreakoutBundle,
    "smc":       SMCBundle,
    "composite": CompositeBundle,
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
        if df is None or len(df) < 30:
            return _empty_result(bundle_name)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(BUNDLE_MAP[bundle_name])
        cerebro.broker.setcash(settings.INITIAL_CAPITAL)
        cerebro.broker.setcommission(commission=0.001)   # 0.1% per side, NSE-realistic

        cerebro.adddata(bt.feeds.PandasData(dataname=df))
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(
            bt.analyzers.SharpeRatio,
            _name="sharpe",
            riskfreerate=0.065,        # 6.5% Indian risk-free rate
            annualize=True,
        )

        results = cerebro.run()
        strat = results[0]
        return _summarise(bundle_name, strat)
    except Exception:
        log.exception("run_bundle failed: symbol=%s bundle=%s", symbol, bundle_name)
        return _empty_result(bundle_name)


def _summarise(bundle_name: str, strat) -> BundleResult:
    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    sh = strat.analyzers.sharpe.get_analysis()

    closed = ta.get("total", {}).get("closed", 0) or 0
    won = ta.get("won", {}).get("total", 0) or 0
    win_rate = (won / closed) if closed > 0 else 0.0

    trades = list(getattr(strat, "trade_log", []) or [])
    if trades:
        avg_return = sum(t.get("pnl_pct", 0.0) for t in trades) / len(trades)
    else:
        avg_return = 0.0

    max_dd = (dd.get("max", {}).get("drawdown", 0.0)) or 0.0
    sharpe_val = sh.get("sharperatio") or 0.0

    return BundleResult(
        bundle_name=bundle_name,
        win_rate=round(win_rate, 3),
        avg_return_pct=round(avg_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe_val, 3),
        total_trades=closed,
        trades=trades,
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
    """Run all 5 peer bundles on a symbol. Returns a dict with exactly 5 keys."""
    return {name: run_bundle(symbol, name, days=days) for name in BUNDLE_MAP}


def select_best_bundles(results: Dict[str, BundleResult]) -> List[str]:
    """Top 2 bundle names by Sharpe across all 5 candidates.

    Bundles with `total_trades == 0` are demoted (treated as Sharpe = -inf) so
    we never pick a bundle that did not actually trade in the window.
    """
    def key(name: str) -> float:
        r = results[name]
        if r.total_trades <= 0:
            return float("-inf")
        return r.sharpe_ratio

    ordered = sorted(BUNDLE_MAP.keys(), key=key, reverse=True)
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
    top = [sym for sym, sharpe, _ in ranked[:TOP_N_CANDIDATES] if sharpe > float("-inf")]
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
            db.add(BacktestResult(
                weekly_run_id=weekly_run_id,
                symbol=symbol,
                run_date=today,
                bundle_name=bundle_name,
                win_rate=r.win_rate,
                avg_return_pct=r.avg_return_pct,
                max_drawdown_pct=r.max_drawdown_pct,
                sharpe_ratio=r.sharpe_ratio,
                total_trades=r.total_trades,
            ))
        db.commit()
