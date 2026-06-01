# 10 — Telegram Bot

> The Telegram bot runs as a **separate process** from `plutus-main`. It is its
> own systemd unit (`plutus-bot.service`) — see `15_deployment.md`. The bot
> handles user commands and also receives push requests from `plutus-main` via
> a small loopback-only FastAPI on `127.0.0.1:8001`.
>
> Module path: `plutus.alerts.telegram_bot`.
> Process entry point: `src/bot.py`.

---

## Setup

1. Message `@BotFather` on Telegram → `/newbot` → get token.
2. Message `@userinfobot` to get your personal chat ID.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

---

## Process Architecture

`plutus-bot` is a single Python process that runs **two cooperating async
servers on the same asyncio event loop**:

| Component | Role |
|---|---|
| `telegram.ext.Application` (polling) | Receives commands from Telegram |
| `FastAPI` on `127.0.0.1:8001` | Receives push requests from `plutus-main` over loopback HTTP |

`plutus-main` (port 8000) and `plutus-bot` (port 8001 internal + Telegram polling) are independent processes. They communicate as follows:

```
┌───────────────────────────┐               ┌──────────────────────────────┐
│  plutus-main.service      │               │  plutus-bot.service          │
│  ─────────────────────    │   POST        │  ─────────────────────       │
│  FastAPI :8000  ──────────┼──/push/*─────►│  FastAPI 127.0.0.1:8001      │
│  APScheduler              │   (loopback)  │                              │
│  /analyze (cache+rl)      │◄──────────────┤  /stock SYMBOL handler       │
└───────────────────────────┘   X-API-Key   │  Telegram polling Application│
                                            └──────────────┬───────────────┘
                                                           │
                                                           ▼
                                                      Telegram API
```

The `/push/*` endpoints are loopback-only (`127.0.0.1`) and intentionally have
**no auth** — the bind address is the boundary. `BOT_INTERNAL_HOST` and
`BOT_INTERNAL_PORT` are configured in `plutus.config.settings` (see
`03_config_env.md`).

---

## `src/bot.py` — process entry point

Cleanest python-telegram-bot v20+ pattern: build the `Application`, build the
internal FastAPI app, then drive both with a single `asyncio.run` that uses
`application.start()` + `application.updater.start_polling()` alongside
`uvicorn.Server.serve()`. Both share the same loop; both stop cleanly on
`SIGTERM`.

```python
# src/bot.py
"""
Entry point for plutus-bot.service.

Runs python-telegram-bot polling + a loopback FastAPI for push IPC on the
same asyncio event loop.
"""
from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn
from fastapi import FastAPI

from plutus.alerts.telegram_bot import build_telegram_app, register_internal_routes
from plutus.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("plutus.bot")


async def _run() -> None:
    # 1. Telegram Application (polling)
    tg_app = build_telegram_app()

    # 2. Internal FastAPI for push IPC; gets a handle to the bot via tg_app.
    api = FastAPI(title="plutus-bot internal", version="1.0.0")
    register_internal_routes(api, tg_app)

    uvicorn_config = uvicorn.Config(
        api,
        host=settings.BOT_INTERNAL_HOST,
        port=settings.BOT_INTERNAL_PORT,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(uvicorn_config)

    # 3. Cooperative shutdown.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    # 4. Start both. ptb v20+ exposes start()/updater.start_polling() so we
    #    can run it inside an existing event loop instead of run_polling().
    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram polling started.")

        serve_task = asyncio.create_task(server.serve(), name="uvicorn-internal")
        log.info("Internal FastAPI listening on %s:%d",
                 settings.BOT_INTERNAL_HOST, settings.BOT_INTERNAL_PORT)

        await stop_event.wait()
        log.info("Shutdown signal received; stopping...")

        server.should_exit = True
        await serve_task
        await tg_app.updater.stop()
        await tg_app.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

Run as: `python -m src.bot` (matches `plutus-bot.service` ExecStart).

---

## `plutus/alerts/telegram_bot.py`

Public surface used by `src/bot.py`:

| Symbol | Purpose |
|---|---|
| `build_telegram_app() -> Application` | Constructs the ptb `Application` and registers every `CommandHandler`. |
| `register_internal_routes(api, tg_app)` | Adds `/push/weekly-summary` and `/push/news-alert` to the loopback FastAPI. |
| `push_weekly_summary(bot, run_id)` | Loads the weekly run + recs from DB and sends the summary. |
| `push_news_alert(bot, event_id)` | Loads a `NewsEvent` row from DB and sends the alert. |
| `cmd_*` | Individual command handlers — full source below. |

```python
# src/plutus/alerts/telegram_bot.py
"""Plutus Telegram bot: command handlers + internal push routes."""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from plutus.backtesting.paper_trader import PaperTrader, list_portfolios
from plutus.backtesting.runner import run_all_bundles
from plutus.config import settings
from plutus.db.models import (
    NewsEvent,
    Recommendation,
    RecommendationVerdict,
    Watchlist,
    WeeklyRun,
)
from plutus.db.session import SessionLocal

log = logging.getLogger(__name__)

REPORTS_DIR = "src/reports/weekly"
PENDING_TTL_SECONDS = 60
INTERNAL_API_BASE = f"http://127.0.0.1:{settings.API_PORT}"


# ── Pending-trade store (in-memory, 60s TTL) ──────────────────────────────────

@dataclass
class PendingTrade:
    side: str          # "BUY" or "SELL"
    portfolio: str
    symbol: str
    price: float
    shares: int
    created_at: float  # time.monotonic()


# Keyed by chat_id → (token, PendingTrade). Only one pending per chat at a time;
# /buy or /sell while another is pending overwrites the older one.
_PENDING: dict[int, tuple[str, PendingTrade]] = {}


def _set_pending(chat_id: int, trade: PendingTrade) -> str:
    token = uuid.uuid4().hex[:8]
    _PENDING[chat_id] = (token, trade)
    return token


def _take_pending(chat_id: int) -> Optional[PendingTrade]:
    """Pop pending trade if present and not expired."""
    entry = _PENDING.pop(chat_id, None)
    if entry is None:
        return None
    _, trade = entry
    if time.monotonic() - trade.created_at > PENDING_TTL_SECONDS:
        return None
    return trade


# ── /start, /help, /health ───────────────────────────────────────────────────

HELP_TEXT = (
    "🚀 *Plutus Trading Engine*\n\n"
    "*Signals*\n"
    "/signals — Latest weekly BUY/WATCH list\n"
    "/stock SYMBOL — On-demand deep analysis (cached 5 min)\n"
    "/backtest SYMBOL — Run all 5 strategy bundles\n\n"
    "*Portfolios*\n"
    "/portfolio list — All mock portfolios\n"
    "/portfolio NAME — Portfolio summary + open positions\n"
    "/portfolio NAME history — Closed-trade log\n"
    "/portfolio new NAME CAPITAL — Create portfolio\n\n"
    "*Trading (paper)*\n"
    "/buy NAME SYMBOL PRICE SHARES — Paper buy (asks /confirm)\n"
    "/sell NAME SYMBOL PRICE SHARES — Paper sell (asks /confirm)\n"
    "/confirm — Execute the pending trade\n"
    "/cancel — Drop the pending trade\n\n"
    "*Watchlist*\n"
    "/watch add SYMBOL\n"
    "/watch remove SYMBOL\n"
    "/watch list\n"
    "/watch SYMBOL — Latest news + analysis for one symbol\n\n"
    "*History*\n"
    "/history YYYY-MM-DD — Past weekly report\n\n"
    "*System*\n"
    "/health — Liveness check\n"
    "/help — This message"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    # Probe plutus-main /health to confirm cross-process IPC works.
    main_status = "down"
    try:
        async with httpx.AsyncClient(timeout=3) as cli:
            resp = await cli.get(f"{INTERNAL_API_BASE}/health")
            main_status = "up" if resp.status_code == 200 else f"http {resp.status_code}"
    except Exception as exc:
        main_status = f"unreachable ({exc.__class__.__name__})"

    await update.message.reply_text(
        "✅ *plutus-bot is running*\n"
        f"plutus-main: `{main_status}`\n"
        f"Time: {datetime.now().strftime('%d %b %Y %H:%M')} IST",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /signals ─────────────────────────────────────────────────────────────────

async def cmd_signals(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show this week's recommendations."""
    with SessionLocal() as db:
        latest = db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        if not latest:
            await update.message.reply_text("No weekly analysis yet. Next run: Sunday 18:00 IST.")
            return

        recs = (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == latest.id)
            .order_by(Recommendation.confidence.desc())
            .all()
        )

    buy = [r for r in recs if r.recommendation == RecommendationVerdict.BUY]
    watch = [r for r in recs if r.recommendation == RecommendationVerdict.WATCH]

    msg = (
        f"📊 *Weekly Picks — {latest.run_date.strftime('%d %b %Y')}*\n"
        f"Market: {latest.market_regime or 'N/A'} | "
        f"Strategy: {latest.strategy_selected or 'N/A'}\n\n"
    )
    if buy:
        msg += f"✅ *BUY ({len(buy)}):*\n"
        for r in buy[:6]:
            note = f" _({r.revalidation_note})_" if r.revalidation_note else ""
            msg += (
                f"• `{r.symbol}` — {r.confidence:.1f}/10 | "
                f"Entry ₹{r.entry_low:.0f}–{r.entry_high:.0f} | "
                f"T1 ₹{r.target1:.0f} | SL ₹{r.stop_loss:.0f}{note}\n"
            )
    if watch:
        msg += f"\n⏳ *WATCH ({len(watch)}):*\n"
        for r in watch[:4]:
            msg += f"• `{r.symbol}` — {r.confidence:.1f}/10\n"

    msg += "\n/stock SYMBOL for full deep-dive."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ── /stock — calls plutus-main /analyze over loopback HTTP ───────────────────

async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    On-demand stock analysis.

    Goes through plutus-main's /analyze endpoint on 127.0.0.1:8000 so it
    benefits from the per-symbol 5-min cache and per-key rate limit (see
    CHANGE_SPEC §6).
    """
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/stock RELIANCE`", parse_mode=ParseMode.MARKDOWN)
        return

    symbol = args[0].upper()
    await update.message.reply_text(
        f"🔍 Analysing *{symbol}*…", parse_mode=ParseMode.MARKDOWN
    )

    try:
        async with httpx.AsyncClient(timeout=60) as cli:
            resp = await cli.post(
                f"{INTERNAL_API_BASE}/analyze",
                headers={"X-API-Key": settings.API_SECRET_KEY},
                json={"symbol": symbol, "exchange": "NSE"},
            )
        if resp.status_code == 429:
            payload = resp.json()
            await update.message.reply_text(
                f"⏳ Rate limit hit. Try again in "
                f"{payload.get('retry_after_seconds', '?')}s."
            )
            return
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"❌ Analysis failed for {symbol}: {exc}")
        return

    result = resp.json()
    await update.message.reply_text(
        _format_analysis(symbol, result), parse_mode=ParseMode.MARKDOWN
    )


# ── /portfolio (list / new / view / history) ─────────────────────────────────

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "/portfolio list\n"
            "/portfolio new NAME CAPITAL\n"
            "/portfolio NAME\n"
            "/portfolio NAME history"
        )
        return

    sub = args[0].lower()

    if sub == "list":
        portfolios = list_portfolios()
        if not portfolios:
            await update.message.reply_text(
                "No mock portfolios yet. Create one: `/portfolio new myport 100000`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        msg = "📁 *Mock Portfolios:*\n"
        for p in portfolios:
            sign = "+" if p["realised_pnl"] >= 0 else ""
            msg += (
                f"• `{p['name']}` — ₹{p['initial_capital']:,.0f} | "
                f"P&L: {sign}₹{p['realised_pnl']:,.0f} "
                f"({sign}{p['realised_pnl_pct']:.2f}%) | "
                f"Win: {p['win_rate']:.0f}% | Open: {p['open_positions']}\n"
            )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    if sub == "new":
        if len(args) < 3:
            await update.message.reply_text("Usage: `/portfolio new NAME CAPITAL`",
                                            parse_mode=ParseMode.MARKDOWN)
            return
        name = args[1]
        try:
            capital = float(args[2])
            PaperTrader.create_portfolio(name, capital)
            await update.message.reply_text(
                f"✅ Created portfolio *{name}* with ₹{capital:,.0f}",
                parse_mode=ParseMode.MARKDOWN,
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        return

    # /portfolio NAME [history]
    name = args[0]
    try:
        pt = PaperTrader(name)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return

    if len(args) >= 2 and args[1].lower() == "history":
        trades = pt.get_trade_history(limit=20)
        if not trades:
            await update.message.reply_text(f"No closed trades in *{name}* yet.",
                                            parse_mode=ParseMode.MARKDOWN)
            return
        lines = [f"📜 *{name}* — last {len(trades)} closed trades"]
        for t in trades:
            sign = "+" if (t["realised_pnl"] or 0) >= 0 else ""
            lines.append(
                f"• `{t['symbol']}` {t['shares']}× "
                f"₹{t['entry_price']:.0f}→₹{t['exit_price']:.0f} "
                f"({t['entry_date']}→{t['exit_date']}) "
                f"{sign}₹{t['realised_pnl']:,.0f} ({sign}{t['realised_pnl_pct']:.2f}%) "
                f"[{t['exit_reason'] or 'MANUAL'}]"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return

    summary = pt.get_summary()
    positions = pt.get_positions()
    sign = "+" if summary["realised_pnl"] >= 0 else ""
    msg = (
        f"💼 *{name}* — ₹{summary['initial_capital']:,.0f} initial\n\n"
        f"Cash: ₹{summary['current_cash']:,.0f}\n"
        f"Current value: ₹{summary['current_value']:,.0f}\n"
        f"Realised P&L: {sign}₹{summary['realised_pnl']:,.0f} "
        f"({sign}{summary['realised_pnl_pct']:.2f}%)\n"
        f"Unrealised P&L: ₹{summary['unrealised_pnl']:,.0f}\n"
        f"Closed trades: {summary['closed_trades']} | "
        f"Win rate: {summary['win_rate']:.0f}%\n"
    )
    if positions:
        msg += "\n*Open Positions:*\n"
        for p in positions:
            sign2 = "+" if p["unrealised_pnl"] >= 0 else ""
            msg += (
                f"• `{p['symbol']}`: {p['shares']} @ ₹{p['entry_price']:.0f} "
                f"({p['entry_date']}) | LTP ₹{p['current_price']:.0f} | "
                f"{sign2}₹{p['unrealised_pnl']:,.0f}\n"
            )
    else:
        msg += "\nNo open positions."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ── /buy → /confirm flow ─────────────────────────────────────────────────────

async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /buy NAME SYMBOL PRICE SHARES

    Runs PaperTrader.compute_pretrade_check(...) WITHOUT writing, prints the
    pre-trade check (CHANGE_SPEC §3), and stores a PendingTrade with 60s TTL.
    User must follow up with /confirm.
    """
    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: `/buy NAME SYMBOL PRICE SHARES`\n"
            "Example: `/buy aggressive RELIANCE 790 50`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    name, symbol, price_str, shares_str = args[0], args[1].upper(), args[2], args[3]
    try:
        price = float(price_str)
        shares = int(shares_str)
        if shares <= 0 or price <= 0:
            raise ValueError("price and shares must be positive")
        pt = PaperTrader(name)
        check = pt.compute_pretrade_check(symbol, price, shares, side="BUY")
    except (ValueError, TypeError) as e:
        await update.message.reply_text(f"❌ {e}")
        return

    if not check["ok_to_proceed"]:
        # Hard reject only on insufficient cash.
        await update.message.reply_text(
            "❌ *Cannot buy:*\n" + "\n".join(f"• {err}" for err in check["errors"]),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    capital = price * shares
    risk_line = (
        f"Risk: ₹{check['risk_inr']:,.0f} ({check['risk_pct']:.2f}% — "
        f"{'within 5% limit ✓' if check['risk_pct'] <= 5 else 'exceeds 5% ⚠'})"
        if check.get("risk_pct") is not None
        else "Risk: not linked to a recommendation (no stop-loss reference)"
    )
    pos_marker = (
        " ⚠" if check["exceeds_advisory_max"] else
        " ✓"
    )
    pos_line = (
        f"Open positions after: {check['open_positions_after']} "
        f"({'above advisory limit of ' + str(check['advisory_max']) + pos_marker if check['exceeds_advisory_max'] else 'within advisory limit ✓'})"
    )
    if check["exceeds_hard_max"]:
        pos_line += f"\n   ⚠⚠ Hard cap is {check['hard_max']} — bot will reject /confirm."

    msg = (
        "⚠️ *Pre-trade check:*\n"
        f"   Shares: {shares} × ₹{price:,.0f} = ₹{capital:,.0f} "
        f"({check['capital_pct']:.1f}% of capital)\n"
        f"   {risk_line}\n"
        f"   {pos_line}\n\n"
        "Confirm? Reply /confirm or /cancel within 60 seconds."
    )

    _set_pending(update.effective_chat.id, PendingTrade(
        side="BUY", portfolio=name, symbol=symbol,
        price=price, shares=shares, created_at=time.monotonic(),
    ))
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ── /sell → /confirm flow ────────────────────────────────────────────────────

async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sell NAME SYMBOL PRICE SHARES

    Like /buy, but the warnings reflect sell-side concerns: realised loss %,
    partial exit, no matching open position.
    """
    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: `/sell NAME SYMBOL PRICE SHARES`\n"
            "Example: `/sell aggressive RELIANCE 770 50`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    name, symbol, price_str, shares_str = args[0], args[1].upper(), args[2], args[3]
    try:
        price = float(price_str)
        shares = int(shares_str)
        if shares <= 0 or price <= 0:
            raise ValueError("price and shares must be positive")
        pt = PaperTrader(name)
        check = pt.compute_pretrade_check(symbol, price, shares, side="SELL")
    except (ValueError, TypeError) as e:
        await update.message.reply_text(f"❌ {e}")
        return

    if not check["ok_to_proceed"]:
        await update.message.reply_text(
            "❌ *Cannot sell:*\n" + "\n".join(f"• {err}" for err in check["errors"]),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    proceeds = price * shares
    lines = [
        "⚠️ *Pre-trade check (SELL):*",
        f"   Shares: {shares} × ₹{price:,.0f} = ₹{proceeds:,.0f}",
    ]
    for w in check["warnings"]:
        lines.append(f"   • {w}")
    lines.append("")
    lines.append("Confirm? Reply /confirm or /cancel within 60 seconds.")

    _set_pending(update.effective_chat.id, PendingTrade(
        side="SELL", portfolio=name, symbol=symbol,
        price=price, shares=shares, created_at=time.monotonic(),
    ))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── /confirm and /cancel ─────────────────────────────────────────────────────

async def cmd_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pending = _take_pending(update.effective_chat.id)
    if pending is None:
        await update.message.reply_text("No pending trade (or it expired). Run /buy or /sell again.")
        return

    try:
        pt = PaperTrader(pending.portfolio)
        if pending.side == "BUY":
            trade_id = pt.buy(pending.symbol, pending.price, pending.shares)
            await update.message.reply_text(
                f"✅ *BUY executed* in `{pending.portfolio}`\n"
                f"• {pending.shares} × {pending.symbol} @ ₹{pending.price:,.2f}\n"
                f"• Capital used: ₹{pending.price * pending.shares:,.0f}\n"
                f"• Trade ID: {trade_id}",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:  # SELL
            result = pt.sell(pending.symbol, pending.price, pending.shares)
            sign = "+" if result["realised_pnl"] >= 0 else ""
            await update.message.reply_text(
                f"✅ *SELL executed* in `{pending.portfolio}`\n"
                f"• {pending.shares} × {pending.symbol} @ ₹{pending.price:,.2f}\n"
                f"• Realised P&L: {sign}₹{result['realised_pnl']:,.0f} "
                f"({sign}{result['realised_pnl_pct']:.2f}%)",
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if _PENDING.pop(update.effective_chat.id, None) is None:
        await update.message.reply_text("No pending trade to cancel.")
    else:
        await update.message.reply_text("✅ Pending trade cancelled.")


# ── /watch (add / remove / list / SYMBOL) ────────────────────────────────────

async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage:\n/watch add SYMBOL\n/watch remove SYMBOL\n/watch list\n/watch SYMBOL"
        )
        return

    sub = args[0].lower()
    with SessionLocal() as db:
        if sub == "add" and len(args) >= 2:
            symbol = args[1].upper()
            existing = db.query(Watchlist).filter(Watchlist.symbol == symbol).first()
            if existing:
                await update.message.reply_text(
                    f"`{symbol}` is already in your watchlist.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                db.add(Watchlist(symbol=symbol, exchange="NSE"))
                db.commit()
                await update.message.reply_text(
                    f"✅ `{symbol}` added to watchlist.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            return

        if sub == "remove" and len(args) >= 2:
            symbol = args[1].upper()
            item = db.query(Watchlist).filter(Watchlist.symbol == symbol).first()
            if item:
                db.delete(item)
                db.commit()
                await update.message.reply_text(
                    f"✅ `{symbol}` removed.", parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    f"`{symbol}` not in watchlist.", parse_mode=ParseMode.MARKDOWN,
                )
            return

        if sub == "list":
            items = db.query(Watchlist).order_by(Watchlist.added_at.desc()).all()
            if not items:
                await update.message.reply_text("Watchlist is empty.")
            else:
                msg = "👁 *Watchlist:*\n" + "\n".join(f"• `{w.symbol}`" for w in items)
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

    # Treat as /watch SYMBOL — last 3 material news events for that symbol.
    symbol = args[0].upper()
    with SessionLocal() as db:
        events = (
            db.query(NewsEvent)
            .filter(NewsEvent.symbol == symbol, NewsEvent.is_material.is_(True))
            .order_by(NewsEvent.published_at.desc())
            .limit(3)
            .all()
        )
    if not events:
        await update.message.reply_text(
            f"No material news for `{symbol}` in DB. Try `/stock {symbol}`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    msg = f"👁 *{symbol}* — last {len(events)} material headlines:\n"
    for e in events:
        ts = e.published_at.strftime("%d %b %H:%M") if e.published_at else "—"
        msg += f"• [{ts}] {e.headline} _({e.source or '?'})_\n"
    msg += f"\n/stock {symbol} for full re-analysis."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ── /history YYYY-MM-DD ──────────────────────────────────────────────────────

async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Open `src/reports/weekly/<date>.md` and send as text (truncated if huge)."""
    args = ctx.args
    if not args:
        files = sorted(glob.glob(f"{REPORTS_DIR}/*.md"), reverse=True)[:5]
        if not files:
            await update.message.reply_text("No history yet.")
            return
        dates = [os.path.basename(f).replace(".md", "") for f in files]
        msg = "📋 *Recent Reports:*\n" + "\n".join(f"• /history {d}" for d in dates)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    date_str = args[0]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await update.message.reply_text("Date must be YYYY-MM-DD.")
        return

    path = f"{REPORTS_DIR}/{date_str}.md"
    if not os.path.exists(path):
        await update.message.reply_text(f"No report for {date_str}.")
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # Telegram message limit is 4096 chars; truncate with a hint to dashboard.
    if len(content) > 3800:
        content = content[:3800] + "\n\n…_(truncated; see dashboard for full report)_"

    await update.message.reply_text(content, parse_mode=ParseMode.MARKDOWN)


# ── /backtest SYMBOL ─────────────────────────────────────────────────────────

async def cmd_backtest(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Run all 5 strategy bundles for the symbol and post a summary."""
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/backtest RELIANCE`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    symbol = args[0].upper()
    await update.message.reply_text(
        f"🧪 Running 5-bundle backtest on *{symbol}*…",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        results = await asyncio.to_thread(run_all_bundles, symbol, 90)
    except Exception as e:
        await update.message.reply_text(f"❌ Backtest failed: {e}")
        return

    lines = [f"🧪 *Backtest — {symbol}* (last 90d)"]
    for name, br in results.items():
        lines.append(
            f"• `{name}` — trades: {br.total_trades} | "
            f"win: {br.win_rate * 100:.0f}% | "
            f"avg ret: {br.avg_return_pct:.2f}% | "
            f"Sharpe: {br.sharpe_ratio:.2f}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Plain-text shortcut: bare SYMBOL → /stock ────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if re.match(r"^[A-Z&]{2,15}$", text.upper()):
        ctx.args = [text.upper()]
        await cmd_stock(update, ctx)


# ── Internal push routes (called by plutus-main over loopback) ───────────────

class WeeklySummaryPush(BaseModel):
    run_id: int


class NewsAlertPush(BaseModel):
    event_id: int


def register_internal_routes(app: FastAPI, tg_app: Application) -> None:
    """
    Mount /push/* on the internal FastAPI. Bound to 127.0.0.1 in src/bot.py;
    no auth needed (loopback is the boundary).
    """

    @app.post("/push/weekly-summary")
    async def _push_weekly(body: WeeklySummaryPush) -> dict:
        try:
            await push_weekly_summary(tg_app.bot, body.run_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"ok": True, "run_id": body.run_id}

    @app.post("/push/news-alert")
    async def _push_news(body: NewsAlertPush) -> dict:
        try:
            await push_news_alert(tg_app.bot, body.event_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"ok": True, "event_id": body.event_id}

    @app.get("/health")
    async def _health() -> dict:
        return {"status": "ok", "service": "plutus-bot"}


# ── Push functions (load from DB → format → send) ────────────────────────────

async def push_weekly_summary(bot: Bot, run_id: int) -> None:
    """Load WeeklyRun + top recs and push the summary to TELEGRAM_CHAT_ID."""
    with SessionLocal() as db:
        run = db.query(WeeklyRun).filter(WeeklyRun.id == run_id).first()
        if run is None:
            raise LookupError(f"weekly_run id={run_id} not found")
        recs = (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == run.id)
            .order_by(Recommendation.confidence.desc())
            .all()
        )

    buy = [r for r in recs if r.recommendation == RecommendationVerdict.BUY]
    watch = [r for r in recs if r.recommendation == RecommendationVerdict.WATCH]

    msg = (
        f"📊 *Weekly Picks Ready — {run.run_date.strftime('%d %b %Y')}*\n"
        f"Market: {run.market_regime or 'N/A'} | "
        f"Strategy: {run.strategy_selected or 'N/A'}\n\n"
    )
    if buy:
        msg += f"✅ *BUY ({len(buy)}):* " + ", ".join(f"`{r.symbol}`" for r in buy[:6]) + "\n"
    if watch:
        msg += f"⏳ *WATCH ({len(watch)}):* " + ", ".join(f"`{r.symbol}`" for r in watch[:4]) + "\n"
    msg += "\n/signals for full details (entry / target / stop)."

    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN,
    )


async def push_news_alert(bot: Bot, event_id: int) -> None:
    """Load NewsEvent and push a formatted alert."""
    with SessionLocal() as db:
        ev = db.query(NewsEvent).filter(NewsEvent.id == event_id).first()
        if ev is None:
            raise LookupError(f"news_event id={event_id} not found")

    icon = "🚨" if ev.sentiment == "negative" else "📢"
    signal = (
        "⬇️ Review SELL/EXIT if holding" if ev.sentiment == "negative"
        else "📈 Monitor closely"
    )
    msg = (
        f"{icon} *NEWS ALERT — {ev.symbol}*\n\n"
        f"{ev.headline}\n\n"
        f"Source: {ev.source or '?'} | Sentiment: {ev.sentiment or 'unknown'}\n"
        f"Signal: {signal}\n"
        f"/stock {ev.symbol} for full re-analysis."
    )
    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN,
    )

    # Mark alert_sent so the news_monitor doesn't double-send.
    with SessionLocal() as db:
        db.query(NewsEvent).filter(NewsEvent.id == event_id).update({"alert_sent": True})
        db.commit()


# ── Formatter for /stock /analyze response ───────────────────────────────────

def _format_analysis(symbol: str, result: dict) -> str:
    rec = result.get("recommendation", "N/A")
    icon = {"BUY": "✅", "SELL": "🔴", "HOLD": "⏸",
            "WATCH": "👀", "AVOID": "❌"}.get(rec, "❓")
    entry = result.get("entry_zone", [0, 0])
    targets = result.get("targets", [0, 0])
    pos = result.get("position", {}) or {}
    cache_tag = " _(cached)_" if result.get("cache_hit") else ""

    return (
        f"📈 *{symbol}* — NSE{cache_tag}\n"
        f"Recommendation: {icon} *{rec}* "
        f"(Confidence: {result.get('confidence', 0):.1f}/10)\n\n"
        f"Entry Zone: ₹{entry[0]:,.0f} – ₹{entry[1]:,.0f}\n"
        f"Target 1: ₹{targets[0]:,.0f} | Target 2: ₹{targets[1]:,.0f}\n"
        f"Stop Loss: ₹{result.get('stop_loss', 0):,.0f}\n"
        f"R:R Ratio: {result.get('risk_reward', 0):.2f}\n\n"
        f"Position: {pos.get('shares', 0)} shares | "
        f"₹{pos.get('capital', 0):,.0f} "
        f"({pos.get('pct_of_portfolio', 0):.1f}% of capital)\n"
        f"Max Loss: ₹{pos.get('max_loss_inr', 0):,.0f} | "
        f"Hold: {result.get('hold_days', 'N/A')} days\n\n"
        f"Strategy: {result.get('strategy', 'N/A')}\n\n"
        f"📝 _{(result.get('reasoning') or '')[:300]}_"
    )


# ── App builder ──────────────────────────────────────────────────────────────

def build_telegram_app() -> Application:
    """Construct the ptb Application and register every command handler."""
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("signals", cmd_signals))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("sell", cmd_sell))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("backtest", cmd_backtest))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app
```

---

## Push IPC — how `plutus-main` calls the bot

`plutus-main`'s scheduler triggers pushes by POSTing to the loopback FastAPI:

```python
# inside plutus-main, e.g. plutus.scheduler.jobs
import httpx
from plutus.config import settings


async def trigger_weekly_push(run_id: int) -> None:
    url = f"http://{settings.BOT_INTERNAL_HOST}:{settings.BOT_INTERNAL_PORT}/push/weekly-summary"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(url, json={"run_id": run_id})
    except httpx.HTTPError as exc:
        # Bot service down: log and continue. The weekly run itself succeeded.
        log.warning("Weekly push to bot failed: %s", exc)


async def trigger_news_push(event_id: int) -> None:
    url = f"http://{settings.BOT_INTERNAL_HOST}:{settings.BOT_INTERNAL_PORT}/push/news-alert"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(url, json={"event_id": event_id})
    except httpx.HTTPError as exc:
        log.warning("News push to bot failed: %s", exc)
```

If `plutus-bot.service` is down, the weekly run still completes — only the
push notification is dropped. The user can always pull via `/signals`.

---

## `/buy` Pre-trade check format

Output produced by `cmd_buy` after calling `PaperTrader.compute_pretrade_check`:

```
⚠️ Pre-trade check:
   Shares: 50 × ₹790 = ₹39,500 (39.5% of capital)
   Risk: ₹1,750 (1.75% — within 5% limit ✓)
   Open positions after: 5 (above advisory limit of 4 ⚠)

Confirm? Reply /confirm or /cancel within 60 seconds.
```

Rules (CHANGE_SPEC §3):

1. **Hard reject only on insufficient cash** — sets `ok_to_proceed=False`, lists the cash shortfall in `errors`. The bot prints "Cannot buy" and does *not* store a pending trade.
2. **All other checks are warnings** (>5% risk, > advisory_max open positions, > hard_max). The bot still asks for `/confirm`.
3. **Pending trades** live in an in-memory `dict[chat_id -> (token, PendingTrade)]` with a 60-second TTL. `/buy` or `/sell` while another is pending overwrites it. `/confirm` calls `PaperTrader.buy(...)` / `.sell(...)` and removes the pending entry. `/cancel` drops it. `_take_pending` checks the TTL before returning.

For `/sell`, the warnings instead come from `compute_pretrade_check(..., side="SELL")`:

- "selling at loss of X.XX%" if `price < weighted_avg_entry`
- "no matching open position" → hard error
- "selling more shares than open" → hard error
- "partial exit (Y of Z shares remaining)" → warning

---

## Bot Command Quick Reference

| Command | Example | Description |
|---|---|---|
| `/start` /  `/help` | `/help` | Show all commands |
| `/health` | `/health` | Liveness check (also probes plutus-main) |
| `/signals` | `/signals` | Latest weekly BUY/WATCH list |
| `/stock SYMBOL` | `/stock RELIANCE` | On-demand analysis (5-min cache) |
| `/backtest SYMBOL` | `/backtest RELIANCE` | Run all 5 strategy bundles |
| `/portfolio list` | `/portfolio list` | All mock portfolios |
| `/portfolio NAME` | `/portfolio aggressive` | Portfolio summary |
| `/portfolio NAME history` | `/portfolio aggressive history` | Closed trade log |
| `/portfolio new NAME CAPITAL` | `/portfolio new aggressive 100000` | Create portfolio |
| `/buy NAME SYMBOL PRICE SHARES` | `/buy aggressive RELIANCE 790 50` | Paper buy → asks /confirm |
| `/sell NAME SYMBOL PRICE SHARES` | `/sell aggressive RELIANCE 770 50` | Paper sell → asks /confirm |
| `/confirm` | `/confirm` | Execute pending trade |
| `/cancel` | `/cancel` | Drop pending trade |
| `/watch add SYMBOL` | `/watch add BAJFINANCE` | Add to watchlist |
| `/watch remove SYMBOL` | `/watch remove WIPRO` | Remove from watchlist |
| `/watch list` | `/watch list` | Show watchlist |
| `/watch SYMBOL` | `/watch RELIANCE` | Last 3 material headlines |
| `/history` | `/history 2026-05-25` | Past weekly report (markdown) |
| Plain text | `TATAMOTORS` | Shortcut for `/stock` |

---

## Cross-references

- Per-symbol `/analyze` cache + 30/hr rate limit: see `09_api.md` and CHANGE_SPEC §6.
- `PaperTrader.compute_pretrade_check`, `.buy`, `.sell`: see `13_mock_portfolios.md`.
- Schema for `mock_portfolios`, `paper_trades`, `linked_recommendation_id`: see `04_database.md`.
- Scheduler jobs that call the push endpoints: see `12_scheduler.md`.
- Systemd unit for `plutus-bot.service`: see `15_deployment.md`.
