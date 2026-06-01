# alerts/telegram_bot.py
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.constants import ParseMode
from plutus.config import settings
from plutus.agents.graph import run_analysis
from plutus.backtesting.paper_trader import PaperTrader, list_portfolios
from plutus.db.session import SessionLocal
from plutus.db.models import Recommendation, WeeklyRun, Watchlist, NewsEvent
from datetime import datetime, date
import asyncio, re

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)


# ── Command Handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *Plutus Trading Engine*\n\n"
        "Commands:\n"
        "/signals — Weekly BUY/WATCH list\n"
        "/stock SYMBOL — Deep analysis\n"
        "/portfolio list — All mock portfolios\n"
        "/portfolio new NAME CAPITAL — Create portfolio\n"
        "/portfolio NAME — View portfolio details\n"
        "/buy NAME SYMBOL PRICE SHARES — Log paper buy\n"
        "/sell NAME SYMBOL PRICE SHARES — Log paper sell\n"
        "/watch add SYMBOL — Add to watchlist\n"
        "/watch list — Show watchlist\n"
        "/watch remove SYMBOL — Remove from watchlist\n"
        "/history DATE — Weekly report (YYYY-MM-DD)\n"
        "/backtest SYMBOL — Run backtest\n"
        "/health — System status",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✅ *Plutus is running*\n"
        f"Time: {datetime.now().strftime('%d %b %Y %H:%M')} IST\n"
        f"Capital: ₹1,00,000 | Max risk: 5%/trade",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_signals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show this week's recommendations."""
    with SessionLocal() as db:
        latest = db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        if not latest:
            await update.message.reply_text("No weekly analysis yet. Run will trigger Sunday 6PM.")
            return

        recs = db.query(Recommendation)\
            .filter(Recommendation.weekly_run_id == latest.id)\
            .order_by(Recommendation.confidence.desc()).all()

        buy = [r for r in recs if r.recommendation.value == "BUY"]
        watch = [r for r in recs if r.recommendation.value == "WATCH"]

        msg = f"📊 *Weekly Picks — {latest.run_date.strftime('%d %b %Y')}*\n"
        msg += f"Market: {latest.market_regime or 'N/A'} | Strategy: {latest.strategy_selected or 'N/A'}\n\n"

        if buy:
            msg += f"✅ *BUY ({len(buy)} stocks):*\n"
            for r in buy[:6]:
                msg += (
                    f"• `{r.symbol}` — Score: {r.confidence:.1f}/10 | "
                    f"Entry: ₹{r.entry_low:.0f}–{r.entry_high:.0f} | "
                    f"T1: ₹{r.target1:.0f} | SL: ₹{r.stop_loss:.0f}\n"
                )

        if watch:
            msg += f"\n⏳ *WATCH ({len(watch)} stocks):*\n"
            for r in watch[:4]:
                msg += f"• `{r.symbol}` — Score: {r.confidence:.1f}/10\n"

        msg += f"\n/stock SYMBOL for full deep dive"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """On-demand stock analysis."""
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /stock RELIANCE")
        return

    symbol = args[0].upper()
    await update.message.reply_text(f"🔍 Analysing *{symbol}*... ⏳ (~20 sec)", parse_mode=ParseMode.MARKDOWN)

    try:
        result = await asyncio.to_thread(run_analysis, symbol)
        msg = _format_analysis(symbol, result)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Analysis failed for {symbol}: {str(e)}")


async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Portfolio commands: list / new / view."""
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
            await update.message.reply_text("No mock portfolios yet. Create one: /portfolio new myport 100000")
            return
        msg = "📁 *Mock Portfolios:*\n"
        for p in portfolios:
            sign = "+" if p["realised_pnl"] >= 0 else ""
            msg += (
                f"• `{p['name']}` — ₹{p['initial_capital']:,.0f} | "
                f"P&L: {sign}₹{p['realised_pnl']:,.0f} ({sign}{p['realised_pnl_pct']:.2f}%) | "
                f"Win: {p['win_rate']:.0f}% | Open: {p['open_positions']}\n"
            )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif sub == "new":
        if len(args) < 3:
            await update.message.reply_text("Usage: /portfolio new NAME CAPITAL")
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
            await update.message.reply_text(f"❌ {str(e)}")

    else:
        # View portfolio by name
        name = args[0]
        try:
            pt = PaperTrader(name)
            summary = pt.get_summary()
            positions = pt.get_open_positions()

            sign = "+" if summary["realised_pnl"] >= 0 else ""
            msg = (
                f"💼 *{name}* — ₹{summary['initial_capital']:,.0f} initial\n\n"
                f"Cash Available: ₹{summary['current_cash']:,.0f}\n"
                f"Realised P&L: {sign}₹{summary['realised_pnl']:,.0f} ({sign}{summary['realised_pnl_pct']:.2f}%)\n"
                f"Trades: {summary['closed_trades']} closed | Win Rate: {summary['win_rate']:.0f}%\n"
            )

            if positions:
                msg += "\n*Open Positions:*\n"
                for p in positions:
                    sign2 = "+" if p["unrealised_pnl"] >= 0 else ""
                    msg += (
                        f"• `{p['symbol']}`: {p['shares']} shares @ ₹{p['entry_price']:.0f} "
                        f"({p['entry_date']}) | Now: ₹{p['current_price']:.0f} | "
                        f"{sign2}₹{p['unrealised_pnl']:,.0f}\n"
                    )
            else:
                msg += "\nNo open positions."

            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except ValueError as e:
            await update.message.reply_text(f"❌ {str(e)}")


async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Log a paper buy: /buy portfolio_name SYMBOL PRICE SHARES"""
    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text("Usage: /buy PORTFOLIO SYMBOL PRICE SHARES\nExample: /buy aggressive_momentum RELIANCE 2389 42")
        return

    portfolio_name, symbol, price_str, shares_str = args[0], args[1].upper(), args[2], args[3]
    try:
        price = float(price_str)
        shares = int(shares_str)
        pt = PaperTrader(portfolio_name)
        trade_id = pt.buy(symbol, price, shares)
        capital = price * shares
        await update.message.reply_text(
            f"✅ *Logged BUY* in `{portfolio_name}`\n"
            f"• {shares} × {symbol} @ ₹{price:,.2f}\n"
            f"• Capital used: ₹{capital:,.0f}\n"
            f"• Trade ID: {trade_id}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Log a paper sell: /sell portfolio_name SYMBOL PRICE SHARES"""
    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text("Usage: /sell PORTFOLIO SYMBOL PRICE SHARES\nExample: /sell aggressive_momentum RELIANCE 2450 42")
        return

    portfolio_name, symbol, price_str, shares_str = args[0], args[1].upper(), args[2], args[3]
    try:
        price = float(price_str)
        shares = int(shares_str)
        pt = PaperTrader(portfolio_name)
        result = pt.sell(symbol, price, shares)
        sign = "+" if result["pnl"] >= 0 else ""
        await update.message.reply_text(
            f"✅ *Logged SELL* in `{portfolio_name}`\n"
            f"• {shares} × {symbol} @ ₹{price:,.2f}\n"
            f"• P&L: {sign}₹{result['pnl']:,.0f} ({sign}{result['pnl_pct']:.2f}%)",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Watchlist management: /watch add SYMBOL / list / remove SYMBOL"""
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage:\n/watch add SYMBOL\n/watch list\n/watch remove SYMBOL")
        return

    sub = args[0].lower()
    with SessionLocal() as db:
        if sub == "add" and len(args) >= 2:
            symbol = args[1].upper()
            existing = db.query(Watchlist).filter(Watchlist.symbol == symbol).first()
            if existing:
                await update.message.reply_text(f"`{symbol}` is already in your watchlist.", parse_mode=ParseMode.MARKDOWN)
            else:
                db.add(Watchlist(symbol=symbol, exchange="NSE"))
                db.commit()
                await update.message.reply_text(f"✅ `{symbol}` added to watchlist.\nYou'll receive news alerts for this stock.", parse_mode=ParseMode.MARKDOWN)

        elif sub == "list":
            items = db.query(Watchlist).order_by(Watchlist.added_at.desc()).all()
            if not items:
                await update.message.reply_text("Watchlist is empty. Add stocks: /watch add RELIANCE")
            else:
                msg = "👁 *Watchlist:*\n" + "\n".join(f"• `{w.symbol}`" for w in items)
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        elif sub == "remove" and len(args) >= 2:
            symbol = args[1].upper()
            item = db.query(Watchlist).filter(Watchlist.symbol == symbol).first()
            if item:
                db.delete(item)
                db.commit()
                await update.message.reply_text(f"✅ `{symbol}` removed.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"`{symbol}` not in watchlist.", parse_mode=ParseMode.MARKDOWN)


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show a past weekly report: /history 2026-05-25"""
    args = ctx.args
    if not args:
        # Show list of available reports
        import os, glob
        files = sorted(glob.glob("reports/weekly/*.md"), reverse=True)[:5]
        if not files:
            await update.message.reply_text("No history yet.")
            return
        dates = [os.path.basename(f).replace(".md", "") for f in files]
        msg = "📋 *Available Reports:*\n" + "\n".join(f"• /history {d}" for d in dates)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    date_str = args[0]
    path = f"reports/weekly/{date_str}.md"
    import os
    if not os.path.exists(path):
        await update.message.reply_text(f"No report found for {date_str}.")
        return

    with open(path) as f:
        content = f.read()

    # Telegram has 4096 char limit
    if len(content) > 3800:
        content = content[:3800] + "\n\n... (truncated, see dashboard for full report)"

    await update.message.reply_text(content, parse_mode=ParseMode.MARKDOWN)


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Handle plain text messages.
    If text looks like a stock symbol (2-10 uppercase letters), treat as /stock.
    """
    text = update.message.text.strip()
    if re.match(r'^[A-Z&]{2,15}$', text.upper()):
        ctx.args = [text.upper()]
        await cmd_stock(update, ctx)


# ── Push Functions (called from scheduler) ───────────────────────────────────

async def send_weekly_summary(buy_list: list, watch_list: list, market_regime: str):
    """Push weekly summary to user's Telegram chat."""
    msg = f"📊 *Weekly Picks Ready*\n\n"
    msg += f"Market: {market_regime}\n\n"

    if buy_list:
        msg += f"✅ *BUY ({len(buy_list)}):* " + ", ".join(f"`{s}`" for s in buy_list[:6]) + "\n"
    if watch_list:
        msg += f"⏳ *WATCH ({len(watch_list)}):* " + ", ".join(f"`{s}`" for s in watch_list[:4]) + "\n"

    msg += "\n/signals for full details with entry/target/stop"
    await bot.send_message(chat_id=settings.TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)


async def send_news_alert(symbol: str, headline: str, sentiment: str, current_price: float, impact: str):
    """Push urgent news alert."""
    icon = "🚨" if sentiment == "negative" else "📢"
    signal = "⬇️ SELL/EXIT if holding" if sentiment == "negative" else "📈 Monitor closely"
    msg = (
        f"{icon} *NEWS ALERT — {symbol}*\n\n"
        f"{headline}\n\n"
        f"Signal: {signal}\n"
        f"Current Price: ₹{current_price:,.2f}\n"
        f"/stock {symbol} for full re-analysis"
    )
    await bot.send_message(chat_id=settings.TELEGRAM_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)


# ── Formatter ─────────────────────────────────────────────────────────────────

def _format_analysis(symbol: str, result: dict) -> str:
    rec = result.get("recommendation", "N/A")
    icon = {"BUY": "✅", "SELL": "🔴", "HOLD": "⏸", "WATCH": "👀", "AVOID": "❌"}.get(rec, "❓")
    entry = result.get("entry_zone", [0, 0])
    targets = result.get("targets", [0, 0])
    pos = result.get("position", {})

    return (
        f"📈 *{symbol}* — NSE\n"
        f"Recommendation: {icon} *{rec}* (Confidence: {result.get('confidence', 0):.1f}/10)\n\n"
        f"Entry Zone: ₹{entry[0]:,.0f} – ₹{entry[1]:,.0f}\n"
        f"Target 1: ₹{targets[0]:,.0f} | Target 2: ₹{targets[1]:,.0f}\n"
        f"Stop Loss: ₹{result.get('stop_loss', 0):,.0f}\n"
        f"R:R Ratio: {result.get('risk_reward', 0):.2f}\n\n"
        f"Position: {pos.get('shares', 0)} shares | ₹{pos.get('capital', 0):,.0f} ({pos.get('pct_of_portfolio', 0):.1f}% of capital)\n"
        f"Max Loss: ₹{pos.get('max_loss_inr', 0):,.0f} | Hold: {result.get('hold_days', 'N/A')} days\n\n"
        f"Strategy: {result.get('strategy', 'N/A')}\n\n"
        f"📝 _{result.get('reasoning', '')[:300]}_"
    )


# ── App Builder ───────────────────────────────────────────────────────────────

def build_telegram_app():
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("signals", cmd_signals))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("sell", cmd_sell))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app
