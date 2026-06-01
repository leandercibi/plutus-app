# 13 — Mock Portfolio System

> Multi-portfolio paper trading. Schema lives in `04_database.md`
> (`mock_portfolios`, `paper_trades`, `linked_recommendation_id` FK).
> Implementation lives in `plutus.backtesting.paper_trader`.
>
> Module path: `plutus.backtesting.paper_trader`.
> Telegram surface that drives it: see `10_telegram_bot.md`.

---

## Concept

The system supports **multiple named mock portfolios**, each with its own capital,
trade history, and P&L tracking. This lets you run the same engine under different
strategies or risk approaches simultaneously, then compare which "version" of
yourself performs best before committing real money.

Example portfolios:

- `aggressive_momentum` — follows Bundle 1 (trend) signals with full sizes
- `conservative_swing` — follows Bundle 5 (composite) only, smaller positions
- `smc_test` — follows Bundle 4 (SMC) signals only
- `weekly_picks` — manually mirrors the weekly recommendation list

---

## Data Model (alignment with `04_database.md`)

```
mock_portfolios
  id | name (UNIQUE) | initial_capital | notes | created_at

paper_trades
  id | portfolio_id (FK) | linked_recommendation_id (FK → recommendations.id)
   | symbol | direction | entry_price | entry_date | shares | capital_used
   | exit_price | exit_date | realised_pnl | realised_pnl_pct
   | strategy_used | status (OPEN/CLOSED) | exit_reason | created_at
```

Enums (`TradeStatus`, `TradeDirection`, `TradeExitReason`) come from
`plutus.db.models`. The schema and ORM bodies are authoritative in `04_database.md`;
this file does not redefine them.

---

## Cash and Value Derivation

`current_cash` is **derived**, not stored. Formula:

```
current_cash = initial_capital
             − sum(open_trades.capital_used)        # cash locked in OPEN positions
             + sum(closed_trades.realised_pnl)      # net P&L from CLOSED positions
```

`current_value` (mark-to-market portfolio value) layers in unrealised P&L:

```
unrealised_pnl  = sum((LTP(symbol) − entry_price) * shares for each OPEN trade)
current_value   = current_cash + sum(open_trades.shares * LTP)
                = initial_capital + realised_pnl + unrealised_pnl
```

LTP is fetched via `plutus.data.ohlcv.fetch_live_price` (yfinance with a short
cache). If the live fetch fails for a symbol, that position contributes
`shares * entry_price` to `current_value` (i.e. unrealised_pnl=0 for that leg)
and a warning is logged.

---

## Per-portfolio P&L Stats

Computed by `PaperTrader.get_summary()` and used by the Telegram `/portfolio`
view and the dashboard:

| Field | Formula |
|---|---|
| `initial_capital` | `mock_portfolios.initial_capital` |
| `realised_pnl` | `Σ realised_pnl over CLOSED trades` |
| `realised_pnl_pct` | `realised_pnl / initial_capital * 100` |
| `unrealised_pnl` | `Σ (fetch_live_price(symbol) − entry_price) * shares over OPEN trades` |
| `unrealised_pnl_pct` | `unrealised_pnl / initial_capital * 100` |
| `current_cash` | formula above |
| `current_value` | `current_cash + Σ shares * LTP over OPEN` |
| `closed_trades` | `count(status == CLOSED)` |
| `open_positions` | `count(status == OPEN)` |
| `wins` | `count(realised_pnl > 0 over CLOSED)` |
| `win_rate` | `wins / closed_trades * 100` (0 if no closed trades) |

---

## `PaperTrader` — full source

```python
# src/plutus/backtesting/paper_trader.py
"""Paper-trading engine for named mock portfolios."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from plutus.config import settings
from plutus.data.ohlcv import fetch_live_price
from plutus.db.models import (
    MockPortfolio,
    PaperTrade,
    Recommendation,
    TradeDirection,
    TradeExitReason,
    TradeStatus,
)
from plutus.db.session import SessionLocal

log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_ltp(symbol: str, fallback: float) -> float:
    """fetch_live_price with a fallback (used for unrealised P&L when offline)."""
    try:
        return float(fetch_live_price(symbol))
    except Exception as exc:                       # noqa: BLE001
        log.warning("fetch_live_price(%s) failed: %s — using fallback %.2f",
                    symbol, exc, fallback)
        return fallback


# ── Top-level helpers ────────────────────────────────────────────────────────

def list_portfolios() -> list[dict]:
    """Returns one summary dict per portfolio (used by /portfolio list)."""
    out = []
    with SessionLocal() as db:
        for p in db.query(MockPortfolio).order_by(MockPortfolio.created_at).all():
            trader = PaperTrader._from_portfolio(p, db)
            out.append(trader.get_summary())
    return out


# ── PaperTrader ──────────────────────────────────────────────────────────────

class PaperTrader:
    """One instance per portfolio. Methods open and manage SessionLocal scopes."""

    # ----- construction ------------------------------------------------------

    def __init__(self, portfolio_name: str) -> None:
        self.portfolio_name = portfolio_name
        with SessionLocal() as db:
            p = (
                db.query(MockPortfolio)
                .filter(MockPortfolio.name == portfolio_name)
                .first()
            )
            if p is None:
                raise ValueError(f"Portfolio '{portfolio_name}' not found")
            self.portfolio_id = p.id
            self.initial_capital = float(p.initial_capital)

    @classmethod
    def _from_portfolio(cls, p: MockPortfolio, db) -> "PaperTrader":
        """Internal: skip the existence query when caller already holds the row."""
        obj = cls.__new__(cls)
        obj.portfolio_name = p.name
        obj.portfolio_id = p.id
        obj.initial_capital = float(p.initial_capital)
        return obj

    @classmethod
    def create_portfolio(cls, name: str, initial_capital: float,
                         notes: str = "") -> int:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        with SessionLocal() as db:
            existing = db.query(MockPortfolio).filter(MockPortfolio.name == name).first()
            if existing:
                raise ValueError(f"Portfolio '{name}' already exists")
            p = MockPortfolio(name=name, initial_capital=initial_capital, notes=notes or None)
            db.add(p)
            db.commit()
            db.refresh(p)
            return p.id

    # ----- pre-trade check (no writes) --------------------------------------

    def compute_pretrade_check(self, symbol: str, price: float, shares: int,
                               side: str) -> dict:
        """
        Run all warnings WITHOUT writing. Called by the Telegram bot before
        showing the /confirm prompt (CHANGE_SPEC §3).

        Returns:
            {
              "ok_to_proceed": bool,         # False ONLY on:
                                             #   BUY: insufficient cash
                                             #   SELL: no matching open shares
              "capital_pct": float,          # this trade as % of initial_capital
              "risk_pct": float | None,      # if linked rec has stop_loss (BUY)
              "risk_inr": float | None,      # absolute risk in ₹
              "open_positions_after": int,
              "advisory_max": int,
              "hard_max": int,
              "exceeds_advisory_max": bool,
              "exceeds_hard_max": bool,
              "warnings": list[str],
              "errors": list[str],
            }
        """
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be 'BUY' or 'SELL'")
        symbol = symbol.upper()
        capital = price * shares
        warnings: list[str] = []
        errors: list[str] = []

        with SessionLocal() as db:
            open_trades = self._open_trades(db)
            closed_trades = self._closed_trades(db)
            cash = self._cash(open_trades, closed_trades)
            advisory_max = settings.MAX_OPEN_POSITIONS_ADVISORY
            hard_max = settings.MAX_OPEN_POSITIONS_HARD

            if side == "BUY":
                # Cash check (HARD)
                ok_cash = capital <= cash
                if not ok_cash:
                    errors.append(
                        f"Insufficient cash: need ₹{capital:,.0f}, "
                        f"have ₹{cash:,.0f}"
                    )

                # Open-positions count (advisory + hard)
                open_after = len(open_trades) + (
                    0 if any(t.symbol == symbol for t in open_trades) else 1
                )
                exceeds_advisory = open_after > advisory_max
                exceeds_hard = open_after > hard_max
                if exceeds_advisory and not exceeds_hard:
                    warnings.append(
                        f"Open positions after: {open_after} "
                        f"(above advisory limit of {advisory_max})"
                    )
                if exceeds_hard:
                    errors.append(
                        f"Open positions after {open_after} would exceed hard "
                        f"cap of {hard_max}"
                    )

                # Risk: only computable if we can find a recent linked rec
                rec = self._latest_recommendation(db, symbol)
                risk_pct: Optional[float] = None
                risk_inr: Optional[float] = None
                if rec is not None and rec.stop_loss is not None:
                    risk_per_share = max(0.0, price - float(rec.stop_loss))
                    risk_inr = risk_per_share * shares
                    risk_pct = risk_inr / self.initial_capital * 100
                    if risk_pct > 5.0:
                        warnings.append(
                            f"Risk ₹{risk_inr:,.0f} ({risk_pct:.2f}%) "
                            "exceeds 5% of initial capital"
                        )

                ok_to_proceed = ok_cash and not exceeds_hard
                return {
                    "ok_to_proceed": ok_to_proceed,
                    "capital_pct": capital / self.initial_capital * 100,
                    "risk_pct": risk_pct,
                    "risk_inr": risk_inr,
                    "open_positions_after": open_after,
                    "advisory_max": advisory_max,
                    "hard_max": hard_max,
                    "exceeds_advisory_max": exceeds_advisory,
                    "exceeds_hard_max": exceeds_hard,
                    "warnings": warnings,
                    "errors": errors,
                }

            # ---- SELL ----
            sym_trades = [t for t in open_trades if t.symbol == symbol]
            shares_open = sum(t.shares for t in sym_trades)
            if shares_open == 0:
                errors.append(f"No OPEN position in {symbol}")
            elif shares > shares_open:
                errors.append(
                    f"Selling {shares} but only {shares_open} shares open in {symbol}"
                )

            wavg_entry = (
                sum(t.entry_price * t.shares for t in sym_trades) / shares_open
                if shares_open else 0.0
            )
            if wavg_entry and price < wavg_entry:
                loss_pct = (price - wavg_entry) / wavg_entry * 100
                warnings.append(
                    f"Selling at loss of {abs(loss_pct):.2f}% vs "
                    f"weighted-avg entry ₹{wavg_entry:,.0f}"
                )
            if shares_open and shares < shares_open:
                warnings.append(
                    f"Partial exit: {shares_open - shares} shares will remain open"
                )

            open_after = len(open_trades) - (1 if shares_open and shares >= shares_open else 0)
            return {
                "ok_to_proceed": not errors,
                "capital_pct": capital / self.initial_capital * 100,
                "risk_pct": None,
                "risk_inr": None,
                "open_positions_after": open_after,
                "advisory_max": advisory_max,
                "hard_max": hard_max,
                "exceeds_advisory_max": False,
                "exceeds_hard_max": False,
                "warnings": warnings,
                "errors": errors,
            }

    # ----- buy ---------------------------------------------------------------

    def buy(self, symbol: str, price: float, shares: int,
            strategy_used: str = "",
            recommendation_id: Optional[int] = None) -> int:
        """
        Insert a new OPEN paper_trade row. Hard-rejects on insufficient cash.

        Returns the new trade_id. Open-positions and risk-% warnings are NOT
        raised here — they are surfaced pre-execution by
        compute_pretrade_check() and shown in the Telegram /confirm prompt.
        """
        if shares <= 0 or price <= 0:
            raise ValueError("price and shares must be positive")
        symbol = symbol.upper()
        capital_used = price * shares

        with SessionLocal() as db:
            cash = self._cash(self._open_trades(db), self._closed_trades(db))
            if capital_used > cash:
                raise ValueError(
                    f"Insufficient cash: need ₹{capital_used:,.0f}, "
                    f"have ₹{cash:,.0f}"
                )

            trade = PaperTrade(
                portfolio_id=self.portfolio_id,
                linked_recommendation_id=recommendation_id,
                symbol=symbol,
                direction=TradeDirection.LONG,
                entry_price=price,
                entry_date=datetime.utcnow(),
                shares=shares,
                capital_used=capital_used,
                strategy_used=strategy_used or None,
                status=TradeStatus.OPEN,
            )
            db.add(trade)
            db.commit()
            db.refresh(trade)
            return trade.id

    # ----- sell (FIFO across open lots) -------------------------------------

    def sell(self, symbol: str, price: float, shares: int) -> dict:
        """
        FIFO close across OPEN lots for `symbol`. Returns realised P&L breakdown.

        Raises if no matching open shares or the request exceeds open shares.
        """
        if shares <= 0 or price <= 0:
            raise ValueError("price and shares must be positive")
        symbol = symbol.upper()

        with SessionLocal() as db:
            open_lots = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == self.portfolio_id,
                    PaperTrade.symbol == symbol,
                    PaperTrade.status == TradeStatus.OPEN,
                )
                .order_by(PaperTrade.entry_date.asc())
                .all()
            )
            shares_open = sum(t.shares for t in open_lots)
            if shares_open == 0:
                raise ValueError(f"No OPEN position in {symbol}")
            if shares > shares_open:
                raise ValueError(
                    f"Selling {shares} but only {shares_open} shares open in {symbol}"
                )

            remaining = shares
            total_pnl = 0.0
            total_capital = 0.0
            closed_ids: list[int] = []

            for lot in open_lots:
                if remaining == 0:
                    break
                # Plutus does not split lots: if remaining < lot.shares we
                # close the full lot anyway (paper trading; simpler accounting).
                # Note: the pre-trade check enforces shares <= shares_open.
                lot_pnl = (price - lot.entry_price) * lot.shares
                lot_pnl_pct = (price - lot.entry_price) / lot.entry_price * 100

                lot.exit_price = price
                lot.exit_date = datetime.utcnow()
                lot.realised_pnl = lot_pnl
                lot.realised_pnl_pct = lot_pnl_pct
                lot.status = TradeStatus.CLOSED
                lot.exit_reason = TradeExitReason.MANUAL

                total_pnl += lot_pnl
                total_capital += lot.capital_used
                closed_ids.append(lot.id)
                remaining -= lot.shares
                if remaining < 0:
                    # User requested fewer shares than the FIFO lot held; we
                    # closed the whole lot. Record the excess as a warning.
                    log.info(
                        "FIFO close in %s: lot %d held %d shares, request was "
                        "for %d — closed full lot.",
                        symbol, lot.id, lot.shares, lot.shares + remaining,
                    )
                    remaining = 0

            db.commit()

            realised_pnl_pct = (
                total_pnl / total_capital * 100 if total_capital else 0.0
            )
            return {
                "symbol": symbol,
                "shares_closed": shares - remaining,
                "exit_price": price,
                "realised_pnl": total_pnl,
                "realised_pnl_pct": realised_pnl_pct,
                "capital_freed": total_capital,
                "closed_trade_ids": closed_ids,
            }

    # ----- read methods ------------------------------------------------------

    def get_positions(self) -> list[dict]:
        """OPEN positions with mark-to-market unrealised P&L."""
        with SessionLocal() as db:
            lots = self._open_trades(db)
            out = []
            for t in lots:
                ltp = _safe_ltp(t.symbol, t.entry_price)
                upnl = (ltp - t.entry_price) * t.shares
                out.append({
                    "trade_id": t.id,
                    "symbol": t.symbol,
                    "shares": t.shares,
                    "entry_price": t.entry_price,
                    "entry_date": t.entry_date.date().isoformat(),
                    "capital_used": t.capital_used,
                    "current_price": ltp,
                    "unrealised_pnl": upnl,
                    "unrealised_pnl_pct": (ltp - t.entry_price) / t.entry_price * 100,
                    "linked_recommendation_id": t.linked_recommendation_id,
                })
            return out

    def get_summary(self) -> dict:
        with SessionLocal() as db:
            open_trades = self._open_trades(db)
            closed_trades = self._closed_trades(db)

            realised_pnl = sum(t.realised_pnl or 0 for t in closed_trades)
            wins = sum(1 for t in closed_trades if (t.realised_pnl or 0) > 0)
            win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0.0
            cash = self._cash(open_trades, closed_trades)

            unrealised_pnl = 0.0
            mtm_open = 0.0
            for t in open_trades:
                ltp = _safe_ltp(t.symbol, t.entry_price)
                unrealised_pnl += (ltp - t.entry_price) * t.shares
                mtm_open += ltp * t.shares

            current_value = cash + mtm_open

            return {
                "name": self.portfolio_name,
                "initial_capital": self.initial_capital,
                "current_cash": cash,
                "current_value": current_value,
                "realised_pnl": realised_pnl,
                "realised_pnl_pct": realised_pnl / self.initial_capital * 100,
                "unrealised_pnl": unrealised_pnl,
                "unrealised_pnl_pct": unrealised_pnl / self.initial_capital * 100,
                "closed_trades": len(closed_trades),
                "open_positions": len(open_trades),
                "wins": wins,
                "win_rate": win_rate,
            }

    def get_trade_history(self, limit: int = 50) -> list[dict]:
        """Closed trades, newest first."""
        with SessionLocal() as db:
            rows = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.portfolio_id == self.portfolio_id,
                    PaperTrade.status == TradeStatus.CLOSED,
                )
                .order_by(PaperTrade.exit_date.desc())
                .limit(limit)
                .all()
            )
            return [{
                "trade_id": t.id,
                "symbol": t.symbol,
                "shares": t.shares,
                "entry_price": t.entry_price,
                "entry_date": t.entry_date.date().isoformat(),
                "exit_price": t.exit_price,
                "exit_date": t.exit_date.date().isoformat() if t.exit_date else None,
                "realised_pnl": t.realised_pnl,
                "realised_pnl_pct": t.realised_pnl_pct,
                "exit_reason": t.exit_reason.value if t.exit_reason else None,
                "strategy_used": t.strategy_used,
                "linked_recommendation_id": t.linked_recommendation_id,
            } for t in rows]

    # ----- internal queries --------------------------------------------------

    def _open_trades(self, db) -> list[PaperTrade]:
        return (
            db.query(PaperTrade)
            .filter(
                PaperTrade.portfolio_id == self.portfolio_id,
                PaperTrade.status == TradeStatus.OPEN,
            )
            .all()
        )

    def _closed_trades(self, db) -> list[PaperTrade]:
        return (
            db.query(PaperTrade)
            .filter(
                PaperTrade.portfolio_id == self.portfolio_id,
                PaperTrade.status == TradeStatus.CLOSED,
            )
            .all()
        )

    def _cash(self, open_trades, closed_trades) -> float:
        invested = sum(t.capital_used for t in open_trades)
        realised = sum(t.realised_pnl or 0 for t in closed_trades)
        return self.initial_capital - invested + realised

    def _latest_recommendation(self, db, symbol: str) -> Optional[Recommendation]:
        """Most recent recommendation for `symbol` — used to source stop_loss."""
        return (
            db.query(Recommendation)
            .filter(Recommendation.symbol == symbol)
            .order_by(Recommendation.created_at.desc())
            .first()
        )
```

`MAX_OPEN_POSITIONS_ADVISORY` (default 4) and `MAX_OPEN_POSITIONS_HARD` (default
10) come from `plutus.config.settings` per CHANGE_SPEC §3.

---

## Telegram Command Flows

The bot's Telegram handlers (see `10_telegram_bot.md`) call `PaperTrader`
exactly as below.

### `/portfolio new NAME CAPITAL`

```
1. cmd_portfolio parses sub == "new", reads NAME and CAPITAL from args.
2. PaperTrader.create_portfolio(name, capital)
     → INSERT mock_portfolios (name, initial_capital=capital)
     → returns new portfolio_id
3. Bot replies "✅ Created portfolio NAME with ₹CAPITAL"
```

### `/buy NAME SYMBOL PRICE SHARES` → `/confirm`

```
1. cmd_buy validates args (shares > 0, price > 0).
2. Constructs PaperTrader(NAME) (raises if portfolio missing).
3. check = pt.compute_pretrade_check(SYMBOL, PRICE, SHARES, side="BUY")
     → reads current open + closed trades, derives cash
     → looks up latest Recommendation for SYMBOL → stop_loss → risk_pct
     → counts open_positions_after, compares to advisory + hard caps
4. If not check["ok_to_proceed"]:
     bot prints "❌ Cannot buy" + check["errors"]; STOP.
5. Else: bot prints the formatted ⚠️ Pre-trade check block,
     stores PendingTrade(side=BUY, ...) in _PENDING[chat_id] with 60s TTL,
     asks for /confirm or /cancel.
6. On /confirm:
     pt.buy(SYMBOL, PRICE, SHARES)
       → cash check (defensive; same hard rule)
       → INSERT paper_trades (status=OPEN, capital_used=PRICE*SHARES)
       → returns trade_id
     bot replies "✅ BUY executed … Trade ID: <id>"
7. On /cancel or 60s timeout:
     PendingTrade dropped, no DB write.
```

### `/sell NAME SYMBOL PRICE SHARES` → `/confirm`

```
1. cmd_sell validates args.
2. PaperTrader(NAME) → check = pt.compute_pretrade_check(..., side="SELL")
     → loads OPEN lots for SYMBOL; computes shares_open and weighted-avg entry
     → if no open shares OR shares > shares_open → errors → ok_to_proceed=False
     → if PRICE < weighted_avg_entry → warning "selling at loss of X%"
     → if shares < shares_open → warning "partial exit: Y shares remain open"
3. If not check["ok_to_proceed"]: bot prints errors and stops.
4. Else: bot prints SELL pre-trade block + warnings, stores PendingTrade(side=SELL),
     asks for /confirm.
5. On /confirm:
     pt.sell(SYMBOL, PRICE, SHARES)
       → FIFO close across OPEN lots (oldest entry_date first)
       → for each lot: realised_pnl = (PRICE − entry_price) * lot.shares
       → UPDATE paper_trades SET status=CLOSED, exit_price, exit_date, realised_pnl
       → returns aggregated pnl breakdown
     bot replies "✅ SELL executed … P&L: ±₹X (±X.XX%)"
```

### `/portfolio NAME`

```
1. PaperTrader(NAME)
2. summary = pt.get_summary()
     → cash + realised + unrealised stats (LTP via fetch_live_price)
3. positions = pt.get_positions()
     → per-OPEN-lot mark-to-market line
4. Bot formats: initial_capital, cash, current_value, realised P&L,
     unrealised P&L, closed-trade count, win rate, then per-position rows.
```

### `/portfolio NAME history`

```
1. PaperTrader(NAME)
2. trades = pt.get_trade_history(limit=20)
3. Bot prints one line per closed trade: SYMBOL N× ENTRY→EXIT (dates) ±P&L [reason]
```

---

## Dashboard Portfolio Tab

The Streamlit Portfolio tab (see `11_dashboard.md`) calls the same
`PaperTrader.get_summary()` / `get_positions()` / `get_trade_history()` methods
the bot uses, plus:

1. **Portfolio selector dropdown** — switch between all named portfolios.
2. **Summary cards** — initial capital, realised P&L, unrealised P&L, win rate, open positions.
3. **Equity curve** — Plotly line chart of cumulative realised P&L over `exit_date`.
4. **Open positions table** — symbol, shares, entry, LTP, unrealised P&L (re-fetches LTP on render).
5. **Closed trade log** — entry/exit/P&L/exit_reason, links to the linked recommendation row.
6. **Comparison table** — every portfolio side-by-side: initial capital, return %, win rate, open count.
7. **Best/worst trade highlight** — top realised gain and worst realised loss per portfolio.

---

## Linking Trades to Recommendations

`paper_trades.linked_recommendation_id` is a nullable FK to
`recommendations.id`. Set it on `pt.buy(..., recommendation_id=<id>)` so
recommendation outcomes can be cross-checked against actual paper performance:

```sql
SELECT r.symbol,
       r.confidence,
       r.recommendation,
       pt.realised_pnl_pct,
       pt.exit_reason
FROM   recommendations r
JOIN   paper_trades pt ON pt.linked_recommendation_id = r.id
WHERE  pt.status = 'CLOSED'
ORDER  BY r.confidence DESC;
-- Did higher-confidence recs actually produce better outcomes?
```

This is also what `outcome_tracker` (see `12_scheduler.md`) uses, in conjunction
with `recommendations.outcome` / `outcome_pct`, to compare model-assumed fill
prices against actual paper-trade fills.

---

## Auto-import from Weekly Picks (out of scope)

An optional mode where the system automatically creates paper trades on the
weekly BUY list and auto-sells on stop/target hits. **Not in MVP.** Implement
after manual paper trading is validated.
