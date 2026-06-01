# Local Testing Guide

## Prerequisites

✓ PostgreSQL 16 running (already set up in Phase 2)
✓ Python 3.11 venv with dependencies (already set up)
✓ `.env` file with API keys (already configured)

## Quick Start

### 1. Start all services
```bash
./local-test.sh
```

This will start:
- **FastAPI + Scheduler** on port 8000
- **Streamlit Dashboard** on port 8501

### 2. Access the dashboard
Open in browser: http://localhost:8501

### 3. Test the API
```bash
# Health check
curl http://localhost:8000/healthz

# API docs (Swagger UI)
open http://localhost:8000/docs

# Test analyze endpoint (requires API key from .env)
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: $(grep API_SECRET_KEY src/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "RELIANCE", "exchange": "NSE"}'
```

### 4. View logs
```bash
# Main service (FastAPI + scheduler)
tail -f logs/main.log

# Dashboard
tail -f logs/dashboard.log
```

### 5. Stop all services
```bash
./local-stop.sh
```

## What to Test

### Dashboard (http://localhost:8501)

1. **🏠 Home Tab**
   - Should show "No weekly runs yet" (database is empty)
   - System status should show services running

2. **📊 Signals Tab**
   - Will be empty until you run a weekly pipeline
   - Test the "Analyze Stock" button with symbol "RELIANCE"

3. **💼 Portfolio Tab**
   - Create a test portfolio first (see below)
   - View open positions and trade history

4. **🧪 Strategy Lab Tab**
   - Will be empty until backtest results exist
   - Shows 5 bundle comparison charts

5. **📰 News Feed Tab**
   - Should show recent classified news (if news monitor ran)

6. **👁 Watchlist Tab**
   - Add symbols to watchlist
   - Trigger on-demand analysis

7. **📋 History Tab**
   - Shows past weekly runs (empty initially)

8. **⚙️ Settings Tab**
   - View redacted config
   - Check systemd status (will show "unknown" on macOS)

### API Endpoints

```bash
# Health check
curl http://localhost:8000/healthz

# Latest weekly recommendations
curl http://localhost:8000/weekly

# On-demand analysis (requires API key)
curl -X POST http://localhost:8000/analyze \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "INFY", "exchange": "NSE"}'
```

## Manual Testing Steps

### Create a Test Portfolio
```bash
cd src
.venv/bin/python -c "
from plutus.db.session import SessionLocal
from plutus.db.models import MockPortfolio
from datetime import datetime

session = SessionLocal()
portfolio = MockPortfolio(
    name='test-portfolio',
    initial_capital=100000.0,
    notes='Local testing portfolio',
    created_at=datetime.now()
)
session.add(portfolio)
session.commit()
print(f'✓ Created portfolio: {portfolio.name} (ID: {portfolio.id})')
session.close()
"
```

### Trigger a Manual Weekly Run (Optional)
```bash
cd src
.venv/bin/python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from main import weekly_pipeline
asyncio.run(weekly_pipeline())
"
```

**Note:** This will take ~20-30 minutes and requires:
- Valid OPENROUTER_API_KEY in .env
- Network access to yfinance, NSE, RSS feeds

### Test Paper Trading
```bash
cd src
.venv/bin/python -c "
from plutus.backtesting.paper_trader import PaperTrader

trader = PaperTrader('test-portfolio')
result = trader.buy('RELIANCE', quantity=10, entry_price=2500.0)
print(f'Buy result: {result}')

summary = trader.get_summary()
print(f'Portfolio: ₹{summary[\"total_value\"]:,.0f}')
"
```

## Troubleshooting

### Port already in use
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill

# Or use the stop script
./local-stop.sh
```

### Database connection error
```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Restart if needed
brew services restart postgresql@16

# Test connection
PGPASSWORD=plutus psql -h 127.0.0.1 -U plutus -d plutus_db -c "SELECT 1"
```

### Config validation error
```bash
# Check .env file
cat src/.env | grep -E "OPENROUTER|TELEGRAM|API_SECRET"

# Verify config loads
cd src
.venv/bin/python -c "from plutus.config import settings; print('✓ Config OK')"
```

### Import errors
```bash
# Reinstall dependencies
cd src
.venv/bin/pip install -r requirements.txt
```

## Expected Behavior

### On First Run
- Dashboard loads but shows "No data yet" in most tabs
- API health check returns `{"status": "ok"}`
- Scheduler jobs are registered but haven't run yet
- Database tables exist but are empty

### After Manual Weekly Run
- Home tab shows latest run summary
- Signals tab shows BUY/WATCH recommendations
- Strategy Lab shows backtest results for 5 bundles
- News feed shows classified headlines

## Next Steps

Once local testing is complete:
1. Commit your changes: `git add . && git commit -m "Ready for deployment"`
2. Push to GitHub/GitLab
3. Follow `deployment/README.md` for OCI deployment
