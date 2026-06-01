# 07 — Backtesting Runner + Paper Trading Engine

> Runs all **5 strategy bundles** (`trend`, `reversal`, `breakout`, `smc`,
> `composite`) per symbol, ranks them by Sharpe, and feeds the weekly pipeline.
> Paper trader implements the `/buy` `/sell` contract from `_CHANGE_SPEC.md` §3.

---

## `src/plutus/backtesting/runner.py`

### Purpose
- Run all **5** strategy bundles against a given symbol over a date window.
- Compute per-bundle metrics: `win_rate`, `avg_return_pct`, `max_drawdown_pct`,
  `sharpe_ratio`, `total_trades`, plus the raw `trades` list.
- `select_best_bundles(results)` picks the **top 2 by Sharpe across all 5**.
- `weekly_pipeline()` ranks every universe symbol by its best bundle's Sharpe
  and forwards the top 20 to the agent pipeline.
- Persist one row **per bundle per symbol per weekly run** in `backtest_results`.

```python
# src/plutus/backtesting/runner.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

import backtrader as bt

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv
from plutus.data.universe import load_universe
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
    universe = load_universe()
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
```

### `backtest_results` schema (one row per bundle per symbol per weekly run)

```sql
CREATE TABLE backtest_results (
    id              SERIAL PRIMARY KEY,
    weekly_run_id   INTEGER NOT NULL REFERENCES weekly_runs(id) ON DELETE CASCADE,
    symbol          VARCHAR(20) NOT NULL,
    run_date        DATE NOT NULL,
    bundle_name     VARCHAR(20) NOT NULL,    -- 'trend' | 'reversal' | 'breakout' | 'smc' | 'composite'
    win_rate        NUMERIC(5, 3) NOT NULL,
    avg_return_pct  NUMERIC(8, 2) NOT NULL,
    max_drawdown_pct NUMERIC(6, 2) NOT NULL,
    sharpe_ratio    NUMERIC(7, 3) NOT NULL,
    total_trades    INTEGER NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (weekly_run_id, symbol, bundle_name)
);
CREATE INDEX idx_backtest_run_symbol ON backtest_results (weekly_run_id, symbol);
CREATE INDEX idx_backtest_bundle ON backtest_results (bundle_name);
```

The `(weekly_run_id, symbol, bundle_name)` UNIQUE key is what enforces "one row
per bundle per weekly run." `select_best_bundles()` is computed on the fly from
the 5-key dict; it is not persisted as a separate column.

---

## `src/plutus/backtesting/paper_trader.py`

### Purpose
Simulates trade execution within a named mock portfolio. Implements the
`/buy` `/sell` contract from `_CHANGE_SPEC.md` §3:

- **Hard reject** when cash is insufficient.
- **Soft warning** when open positions would exceed
  `MAX_OPEN_POSITIONS_ADVISORY` (returned alongside the trade id; the trade is
  still recorded — `MAX_OPEN_POSITIONS_HARD` is the only hard cap).
- **Soft warning** when the trade's risk (vs the linked recommendation's stop
  loss) exceeds `RISK_PCT_PER_TRADE` of `initial_capital`.

```python
# src/plutus/backtesting/paper_trader.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from plutus.config import settings
from plutus.data.ohlcv import fetch_live_price
from plutus.db.models import (
    MockPortfolio,
    PaperTrade,
    Recommendation,
    TradeDirection,
    TradeStatus,
)
from plutus.db.session import SessionLocal


@dataclass
class BuyResult:
    """Returned by PaperTrader.buy() — trade is always recorded if cash sufficient."""
    trade_id: int
    capital_used: float
    risk_pct: Optional[float]      # None when no recommendation/stop linked
    warnings: List[str]            # human-readable advisory strings; may be empty


class PaperTrader:
    """Per-portfolio paper trading engine."""

    def __init__(self, portfolio_name: str):
        self.portfolio_name = portfolio_name
        self._ensure_portfolio_exists()

    # ------------------------------------------------------------------ #
    # Portfolio lifecycle
    # ------------------------------------------------------------------ #
    def _ensure_portfolio_exists(self) -> None:
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            if not portfolio:
                raise ValueError(
                    f"Portfolio '{self.portfolio_name}' not found. Create it first."
                )

    @staticmethod
    def create_portfolio(name: str, initial_capital: float, notes: str = "") -> MockPortfolio:
        with SessionLocal() as db:
            existing = db.query(MockPortfolio).filter(MockPortfolio.name == name).first()
            if existing:
                raise ValueError(f"Portfolio '{name}' already exists.")
            portfolio = MockPortfolio(
                name=name,
                initial_capital=initial_capital,
                current_cash=initial_capital,
                notes=notes,
            )
            db.add(portfolio)
            db.commit()
            db.refresh(portfolio)
            return portfolio

    # ------------------------------------------------------------------ #
    # Buy
    # ------------------------------------------------------------------ #
    def buy(
        self,
        symbol: str,
        price: float,
        shares: int,
        strategy_used: str = "",
        recommendation_id: Optional[int] = None,
    ) -> BuyResult:
        """Record a paper buy.

        Hard reject (raises ValueError):
            - cash insufficient for `price * shares`
            - open positions would exceed `MAX_OPEN_POSITIONS_HARD`

        Soft warnings (returned in BuyResult.warnings, trade is still recorded):
            - open positions after this trade exceeds `MAX_OPEN_POSITIONS_ADVISORY`
            - trade risk (using rec.stop_loss) exceeds `RISK_PCT_PER_TRADE`
              of initial_capital
        """
        if shares <= 0:
            raise ValueError("shares must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")

        capital_used = price * shares
        warnings: List[str] = []
        risk_pct: Optional[float] = None

        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )

            # ---- HARD REJECT: cash --------------------------------------
            if capital_used > portfolio.current_cash:
                raise ValueError(
                    f"Insufficient cash: need ₹{capital_used:,.0f}, "
                    f"have ₹{portfolio.current_cash:,.0f}"
                )

            # ---- HARD REJECT: position hard cap -------------------------
            open_count = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .count()
            )
            if open_count + 1 > settings.MAX_OPEN_POSITIONS_HARD:
                raise ValueError(
                    f"Hard cap reached: cannot exceed "
                    f"{settings.MAX_OPEN_POSITIONS_HARD} open positions"
                )

            # ---- SOFT WARNING: positions advisory -----------------------
            if open_count + 1 > settings.MAX_OPEN_POSITIONS_ADVISORY:
                warnings.append(
                    f"Open positions after this trade: {open_count + 1} "
                    f"(advisory limit {settings.MAX_OPEN_POSITIONS_ADVISORY})"
                )

            # ---- SOFT WARNING: per-trade risk vs recommendation stop ----
            if recommendation_id is not None:
                rec = db.query(Recommendation).get(recommendation_id)
                if rec and rec.stop_loss:
                    per_share_risk = max(price - float(rec.stop_loss), 0.0)
                    trade_risk = per_share_risk * shares
                    if portfolio.initial_capital > 0:
                        risk_pct = round(
                            trade_risk / float(portfolio.initial_capital) * 100, 2
                        )
                        if risk_pct > settings.RISK_PCT_PER_TRADE:
                            warnings.append(
                                f"Risk on this trade is {risk_pct:.2f}% of "
                                f"initial capital (limit "
                                f"{settings.RISK_PCT_PER_TRADE:.1f}%)"
                            )

            # ---- record trade -------------------------------------------
            trade = PaperTrade(
                portfolio_id=portfolio.id,
                symbol=symbol.upper(),
                direction=TradeDirection.LONG,
                entry_price=price,
                entry_date=datetime.utcnow(),
                shares=shares,
                capital_used=capital_used,
                strategy_used=strategy_used,
                status=TradeStatus.OPEN,
                linked_recommendation_id=recommendation_id,
            )
            portfolio.current_cash = float(portfolio.current_cash) - capital_used
            db.add(trade)
            db.commit()
            db.refresh(trade)

            if warnings:
                warnings.append(f"trade_id={trade.id}")

            return BuyResult(
                trade_id=trade.id,
                capital_used=round(capital_used, 2),
                risk_pct=risk_pct,
                warnings=warnings,
            )

    # ------------------------------------------------------------------ #
    # Sell
    # ------------------------------------------------------------------ #
    def sell(self, symbol: str, price: float, shares: int) -> Dict:
        """Close (or partially close) the oldest open position for `symbol`.

        Returns: {trade_id, shares_closed, realised_pnl, realised_pnl_pct,
                  remaining_shares}
        """
        if shares <= 0:
            raise ValueError("shares must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")

        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            trade = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.symbol == symbol.upper(),
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .order_by(PaperTrade.entry_date.asc())
                .first()
            )
            if not trade:
                raise ValueError(
                    f"No open position for {symbol} in portfolio "
                    f"'{self.portfolio_name}'"
                )

            close_shares = min(shares, trade.shares)
            entry = float(trade.entry_price)
            realised_pnl = (price - entry) * close_shares
            realised_pnl_pct = (price - entry) / entry * 100.0
            proceeds = price * close_shares

            remaining = trade.shares - close_shares
            if remaining == 0:
                trade.exit_price = price
                trade.exit_date = datetime.utcnow()
                trade.realised_pnl = round(realised_pnl, 2)
                trade.realised_pnl_pct = round(realised_pnl_pct, 2)
                trade.status = TradeStatus.CLOSED
            else:
                # Partial close: split into a closed sibling and shrink the open trade.
                closed_sibling = PaperTrade(
                    portfolio_id=portfolio.id,
                    symbol=trade.symbol,
                    direction=trade.direction,
                    entry_price=entry,
                    entry_date=trade.entry_date,
                    shares=close_shares,
                    capital_used=entry * close_shares,
                    strategy_used=trade.strategy_used,
                    linked_recommendation_id=trade.linked_recommendation_id,
                    status=TradeStatus.CLOSED,
                    exit_price=price,
                    exit_date=datetime.utcnow(),
                    realised_pnl=round(realised_pnl, 2),
                    realised_pnl_pct=round(realised_pnl_pct, 2),
                )
                db.add(closed_sibling)
                trade.shares = remaining
                trade.capital_used = float(trade.capital_used) - (entry * close_shares)

            portfolio.current_cash = float(portfolio.current_cash) + proceeds
            db.commit()

            return {
                "trade_id": trade.id,
                "shares_closed": close_shares,
                "realised_pnl": round(realised_pnl, 2),
                "realised_pnl_pct": round(realised_pnl_pct, 2),
                "remaining_shares": remaining,
            }

    # ------------------------------------------------------------------ #
    # Read APIs
    # ------------------------------------------------------------------ #
    def get_positions(self) -> List[Dict]:
        """Open positions for this portfolio with mark-to-market unrealised P&L."""
        out: List[Dict] = []
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            open_trades = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == portfolio.id,
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .order_by(PaperTrade.entry_date.asc())
                .all()
            )
            for t in open_trades:
                try:
                    ltp = fetch_live_price(t.symbol)
                    unreal = (ltp - float(t.entry_price)) * t.shares
                    unreal_pct = (ltp - float(t.entry_price)) / float(t.entry_price) * 100
                except Exception:
                    ltp = float(t.entry_price)
                    unreal = 0.0
                    unreal_pct = 0.0
                out.append({
                    "trade_id": t.id,
                    "symbol": t.symbol,
                    "shares": t.shares,
                    "entry_price": float(t.entry_price),
                    "entry_date": t.entry_date.isoformat(),
                    "current_price": round(ltp, 2),
                    "unrealised_pnl": round(unreal, 2),
                    "unrealised_pnl_pct": round(unreal_pct, 2),
                    "capital_used": float(t.capital_used),
                    "strategy_used": t.strategy_used or "",
                    "linked_recommendation_id": t.linked_recommendation_id,
                })
        return out

    def get_summary(self) -> Dict:
        """Portfolio-level snapshot."""
        with SessionLocal() as db:
            portfolio = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == self.portfolio_name)
                .first()
            )
            all_trades = (
                db.query(PaperTrade)
                .filter(PaperTrade.portfolio_id == portfolio.id)
                .all()
            )
            closed = [t for t in all_trades if t.status == TradeStatus.CLOSED]
            open_trades = [t for t in all_trades if t.status == TradeStatus.OPEN]

            realised_pnl = sum(float(t.realised_pnl or 0) for t in closed)
            wins = [t for t in closed if float(t.realised_pnl or 0) > 0]
            win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0

            unrealised_pnl = 0.0
            mtm_value = 0.0
            for t in open_trades:
                try:
                    ltp = fetch_live_price(t.symbol)
                except Exception:
                    ltp = float(t.entry_price)
                unrealised_pnl += (ltp - float(t.entry_price)) * t.shares
                mtm_value += ltp * t.shares

            current_value = float(portfolio.current_cash) + mtm_value

            return {
                "initial_capital": float(portfolio.initial_capital),
                "current_cash": round(float(portfolio.current_cash), 2),
                "current_value": round(current_value, 2),
                "realised_pnl": round(realised_pnl, 2),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "win_rate": round(win_rate, 1),
                "open_count": len(open_trades),
                "closed_count": len(closed),
            }


def list_portfolios() -> List[Dict]:
    """Lightweight listing for the dashboard / Telegram `/portfolios`."""
    out: List[Dict] = []
    with SessionLocal() as db:
        portfolios = db.query(MockPortfolio).all()
        for p in portfolios:
            closed = [t for t in p.trades if t.status == TradeStatus.CLOSED]
            open_trades = [t for t in p.trades if t.status == TradeStatus.OPEN]
            realised = sum(float(t.realised_pnl or 0) for t in closed)
            wins = [t for t in closed if float(t.realised_pnl or 0) > 0]
            win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
            out.append({
                "name": p.name,
                "initial_capital": float(p.initial_capital),
                "current_cash": round(float(p.current_cash), 2),
                "realised_pnl": round(realised, 2),
                "win_rate": round(win_rate, 1),
                "open_count": len(open_trades),
                "closed_count": len(closed),
                "created_at": p.created_at.strftime("%Y-%m-%d"),
            })
    return out
```

### Required `config.py` constants

```python
# in plutus/config.py — already covered by _CHANGE_SPEC §3 / §6
INITIAL_CAPITAL: float = 100_000.0
MAX_OPEN_POSITIONS_ADVISORY: int = 4
MAX_OPEN_POSITIONS_HARD: int = 10
RISK_PCT_PER_TRADE: float = 5.0     # % of initial_capital per trade
```

### Telegram `/buy` flow integration

`bot.py`'s `/buy` handler calls `PaperTrader.buy(...)`. The returned
`BuyResult.warnings` list is rendered into the pre-trade check message
(see `_CHANGE_SPEC.md` §3); the bot then asks for `/confirm` or `/cancel`
within 60 seconds. A `ValueError` from `buy()` (cash insufficient or hard cap)
is rendered as a hard rejection with no confirm prompt.

---

## Verification

```bash
cd /Users/leander/personal-projects/plutus-app

# Imports resolve under the new module layout.
PYTHONPATH=src python -c "from plutus.backtesting.runner import run_all_bundles, select_best_bundles, BundleResult; print('ok')"
PYTHONPATH=src python -c "from plutus.backtesting.paper_trader import PaperTrader, BuyResult; print('ok')"

# Smoke-test the runner against a single symbol.
PYTHONPATH=src python -c "
from plutus.backtesting.runner import run_all_bundles, select_best_bundles
results = run_all_bundles('RELIANCE', days=90)
assert set(results.keys()) == {'trend','reversal','breakout','smc','composite'}, results.keys()
print('bundles:', list(results.keys()))
print('top 2:', select_best_bundles(results))
"

# DB smoke-test for paper trader.
PYTHONPATH=src python -c "
from plutus.backtesting.paper_trader import PaperTrader
PaperTrader.create_portfolio('smoke', initial_capital=100000)
pt = PaperTrader('smoke')
res = pt.buy('RELIANCE', price=1500.0, shares=10, strategy_used='trend')
print('buy:', res)
print('positions:', pt.get_positions())
print('summary:', pt.get_summary())
"
```

Expected: `run_all_bundles` returns exactly **5** keys; `select_best_bundles`
returns a `List[str]` of length 2; `PaperTrader.buy` returns a `BuyResult`
with `trade_id`, `capital_used`, optional `risk_pct`, and `warnings`.
