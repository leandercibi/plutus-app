# Plutus Dashboard - Complete User Guide

## 🎯 Quick Start

**Dashboard URL:** http://localhost:8501 (local) or https://your-domain.com (production)

---

## 📊 Tab-by-Tab Guide

### 1. 🏠 Home Tab

**Purpose:** Overview of latest weekly run and system status

**What you see:**
- Latest weekly run summary (date, BUY/WATCH counts)
- Top recommendations with confidence scores
- Portfolio P&L summary
- System status (services running)

**Actions:** None (read-only overview)

---

### 2. 📊 Signals Tab

**Purpose:** View latest recommendations and run on-demand analysis

**What you see:**
- Latest BUY recommendations table
- Latest WATCH recommendations table
- On-demand analysis section

**Buttons:**
- **Symbol Input Field:** Enter NSE stock symbol (e.g., RELIANCE, INFY, TCS)
- **Analyze Button:** 
  - Runs full 5-agent LLM analysis (~30 seconds)
  - Calls: Technical, Sentiment, SmartMoney, RiskManager, Synthesizer agents
  - Returns: BUY/SELL/HOLD/WATCH/AVOID with confidence score
  - Shows: Entry zone, targets (T1, T2), stop loss

**How to use:**
1. Enter symbol in text field (e.g., "RELIANCE")
2. Click "Analyze" button
3. Wait 30 seconds for agent pipeline
4. View recommendation with entry/exit levels

---

### 3. 💼 Portfolio Tab

**Purpose:** Paper trading - track positions, execute trades, view P&L

**What you see:**
- Portfolio selector dropdown
- Portfolio metrics (Total Value, Cash, Unrealised P&L, Win Rate, Open Positions)
- Open Positions table (Symbol, Side, Entry Price, Shares, Current Price, P&L)
- Trade History table (closed positions with realized P&L)
- Equity curve chart (cumulative P&L over time)

**Buttons:**

1. **Portfolio Selector Dropdown:**
   - Choose which portfolio to view
   - Default: "test-local" (created during setup)

2. **Check Button:**
   - **Purpose:** Pre-trade risk validation
   - **What it does:** 
     - Checks if you have enough cash for BUY
     - Checks if you're at position limit (10 max)
     - Shows warning if trade would fail
   - **When to use:** Before executing a trade

3. **Buy Button:**
   - **Purpose:** Execute paper BUY trade
   - **Inputs needed:** Symbol, Shares, Entry Price
   - **What it does:**
     - Deducts cash from portfolio
     - Creates open position
     - Tracks unrealized P&L
   - **Example:** Buy 10 shares of RELIANCE at ₹2500

4. **Sell Button:**
   - **Purpose:** Close an open position
   - **What it does:**
     - Closes the position
     - Realizes P&L
     - Adds cash back to portfolio
   - **When to use:** When you want to exit a position

**How to see shares bought:**
1. Select portfolio from dropdown
2. Scroll to "Open Positions" table
3. Each row shows: Symbol, Side (LONG/SHORT), Entry Price, **Shares**, Current Price, P&L
4. For closed positions: Scroll to "Trade History" table

**How to add a new portfolio:**

Currently requires database insert. Run this in terminal:

```bash
cd /Users/leander/personal-projects/plutus-app/src
.venv/bin/python -c "
from plutus.db.session import SessionLocal
from plutus.db.models import MockPortfolio
from datetime import datetime

session = SessionLocal()
portfolio = MockPortfolio(
    name='my-aggressive-portfolio',
    initial_capital=500000.0,
    notes='High risk portfolio',
    created_at=datetime.now()
)
session.add(portfolio)
session.commit()
print(f'✓ Created portfolio: {portfolio.name}')
session.close()
"
```

Then refresh the dashboard - new portfolio will appear in dropdown.

---

### 4. 🧪 Strategy Lab Tab

**Purpose:** View backtest results for all 5 strategy bundles

**What you see:**
- 5 bundle comparison table (Sharpe, Win Rate, Total Trades, Avg P&L)
- Per-bundle equity curves
- Best bundle selection (top 3 by Sharpe ratio)

**Buttons:** None (read-only)

**When data appears:** After first weekly pipeline run or manual backtest

---

### 5. 📰 News Feed Tab

**Purpose:** View material news events classified by LLM

**What you see:**
- Material news events table (Headline, Symbol, Sentiment, Classification, Timestamp)
- Symbol filter dropdown
- Rejected headlines count

**Buttons:**
- **Symbol Filter Dropdown:** Filter news by specific stock
- **Refresh Button:** Reload latest news from database

**When data appears:** After news monitor cron job runs (hourly during market hours)

---

### 6. 👁 Watchlist Tab

**Purpose:** Track custom symbols and run quick analysis

**What you see:**
- Watchlist table (Symbol, Added Date, Notes)
- Add symbol section
- Quick analysis buttons per symbol

**Buttons:**

1. **Symbol Input Field:** Enter symbol to add (e.g., "INFY")
2. **Add Button:** 
   - Adds symbol to watchlist
   - Persists in database
3. **Remove Button:** (per row)
   - Removes symbol from watchlist
4. **Analyze Button:** (per row)
   - Quick analysis for that symbol
   - Same as Signals tab analysis

**How to use:**
1. Enter symbol in input field
2. Click "Add" button
3. Symbol appears in table
4. Click "Analyze" next to any symbol for on-demand analysis

---

### 7. 📋 History Tab

**Purpose:** View past weekly runs and their outcomes

**What you see:**
- Weekly run selector dropdown
- Recommendations table for selected run
- Outcome stats (HIT_T1, HIT_T2, STOPPED, EXPIRED, PENDING)
- Equity curve for that run

**Buttons:**
- **Run Selector Dropdown:** Choose past weekly run by date

**When data appears:** After first weekly pipeline run

---

### 8. ⚙️ Settings Tab

**Purpose:** View configuration and system status

**What you see:**
- Configuration JSON (secrets redacted with ***)
- Systemd service status (plutus-main, plutus-bot, plutus-dashboard, postgresql)
- About section (version, description)

**Buttons:** None (read-only)

**What's redacted:**
- API_SECRET_KEY
- OPENROUTER_API_KEY
- TELEGRAM_BOT_TOKEN
- NEWS_API_KEY
- DB_PASSWORD

---

## 🔄 Typical Workflows

### Workflow 1: Weekly Analysis Review
1. Go to **Home** tab → See latest run summary
2. Go to **Signals** tab → Review BUY recommendations
3. Go to **Portfolio** tab → Execute paper trades based on signals
4. Go to **Strategy Lab** tab → Check which bundles performed best

### Workflow 2: On-Demand Stock Analysis
1. Go to **Signals** tab
2. Enter symbol (e.g., "RELIANCE")
3. Click "Analyze" button
4. Wait 30 seconds
5. Review recommendation and entry/exit levels
6. Go to **Portfolio** tab → Execute trade if BUY signal

### Workflow 3: Portfolio Management
1. Go to **Portfolio** tab
2. Select portfolio from dropdown
3. Review open positions and P&L
4. Click "Check" button before new trade
5. Enter symbol, shares, price
6. Click "Buy" button to execute
7. Monitor position in "Open Positions" table
8. Click "Sell" button when target/stop hit

### Workflow 4: News Monitoring
1. Go to **News Feed** tab
2. Filter by symbol if needed
3. Review material events
4. Check sentiment (POSITIVE/NEGATIVE/NEUTRAL)
5. Go to **Signals** tab → Analyze affected symbols

### Workflow 5: Watchlist Tracking
1. Go to **Watchlist** tab
2. Add symbols you want to track
3. Click "Analyze" next to any symbol for quick check
4. Review results
5. Go to **Portfolio** tab → Execute trade if signal is good

---

## 📸 Button Screenshots

All button interactions captured in: `screenshots/buttons/`

- `portfolio_before_check.png` - Before clicking Check button
- `portfolio_after_check.png` - After clicking Check button (shows validation result)
- `signals_ready_to_analyze.png` - Signals tab with symbol entered
- `watchlist_add_button.png` - Watchlist add symbol interface
- `news_feed_buttons.png` - News feed filter buttons
- `final_home.png` - Home tab final state
- `final_signals.png` - Signals tab final state
- `final_portfolio.png` - Portfolio tab final state
- `final_watchlist.png` - Watchlist tab final state

---

## ❓ FAQ

**Q: How do I add a new portfolio?**  
A: Run the Python script in the "Portfolio Tab" section above. No UI button yet (Phase 9 enhancement).

**Q: How do I see how many shares I bought?**  
A: Portfolio tab → Select portfolio → "Open Positions" table → "Shares" column.

**Q: What does the Check button do?**  
A: Pre-trade risk validation. Checks if you have enough cash and haven't hit position limits.

**Q: Why is my data empty?**  
A: Database is empty until first weekly pipeline runs. Either wait for Monday 9:00 AM IST cron job, or run manually: `cd src && .venv/bin/python -c "import asyncio; from main import weekly_pipeline; asyncio.run(weekly_pipeline())"`

**Q: How long does Analyze take?**  
A: ~30 seconds. It calls 5 LLM agents sequentially (Technical → Sentiment → SmartMoney → RiskManager → Synthesizer).

**Q: Can I trade real money?**  
A: No. This is paper trading only. All trades are simulated in the database.

**Q: How do I deploy to production?**  
A: Follow `deployment/README.md` for OCI deployment with systemd services.

---

## 🎯 Production Checklist

Before going live:
- [ ] Add real OPENROUTER_API_KEY to `.env`
- [ ] Add real TELEGRAM_BOT_TOKEN to `.env` (if using bot)
- [ ] Configure Cloudflare Tunnel for public dashboard URL
- [ ] Run first weekly pipeline to populate data
- [ ] Create production portfolios
- [ ] Test all buttons in production environment
- [ ] Monitor logs for errors
- [ ] Set up alerts for failed cron jobs

---

**Last Updated:** 2026-05-31  
**Version:** 1.0  
**Status:** Production-Ready ✅
