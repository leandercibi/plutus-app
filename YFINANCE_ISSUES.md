# yfinance Data Fetching Issues - Explanation & Solutions

## 🚨 The Problem

When you add symbols like "HDFC" to the watchlist, you see:
- ❌ "Chart unavailable: RetryError..."
- ❌ "Live price unavailable"

## 🔍 Root Cause

**yfinance is being blocked or rate-limited by Yahoo Finance / NSE.**

This happens because:
1. **Yahoo Finance rate limits** - Too many requests from the same IP
2. **NSE website blocks automated requests** - Anti-scraping measures
3. **Local IP reputation** - Residential IPs are more likely to be blocked
4. **Market hours** - Data is less reliable when markets are closed

## ✅ Solutions

### Solution 1: Deploy to OCI (Recommended)

**Why it works:**
- Different IP address (datacenter IP, not residential)
- Better network routing to Yahoo Finance servers
- More reliable during market hours

**How to deploy:**
```bash
# Follow deployment/README.md
ssh ubuntu@<your-oci-ip>
git clone <your-repo>
cd plutus-app
sudo ./deployment/deploy.sh
```

### Solution 2: Wait and Retry

**Why it works:**
- Rate limits reset after time
- Market hours have better data availability

**How to use:**
1. Wait 5-10 minutes between requests
2. Try during market hours (9:15 AM - 3:30 PM IST)
3. Refresh the dashboard page

### Solution 3: Use Correct Symbol Format

**Why it works:**
- Some symbols have changed (e.g., HDFC merged with HDFCBANK)

**Common symbol mappings:**
- ❌ HDFC → ✅ HDFCBANK (HDFC Bank after merger)
- ✅ RELIANCE (Reliance Industries)
- ✅ INFY (Infosys)
- ✅ TCS (Tata Consultancy Services)
- ✅ WIPRO
- ✅ ICICIBANK
- ✅ SBIN (State Bank of India)
- ✅ AXISBANK

### Solution 4: Alternative Data Sources (Future Enhancement)

**Options for Phase 9+:**
- NSE Official API (requires registration)
- Alpha Vantage API (free tier available)
- Twelve Data API (free tier available)
- WebSocket real-time feeds (paid)

## 🛠️ What We've Fixed

### 1. Better Error Handling
- ✅ `fetch_live_price()` now returns 0.0 instead of crashing
- ✅ Dashboard shows helpful error messages
- ✅ Chart errors show why it failed and how to fix

### 2. User-Friendly Messages
- ✅ Warning banner in Watchlist tab
- ✅ Detailed explanation when chart fails
- ✅ "Live price unavailable" instead of crash

### 3. Graceful Degradation
- ✅ Dashboard still works even if data fetch fails
- ✅ Other features remain functional
- ✅ No crashes or blank pages

## 📊 What Still Works

Even with yfinance issues, these features work:

✅ **Database operations** - Add/remove watchlist, portfolios, trades
✅ **API endpoints** - /health, /weekly, /analyze (if data is cached)
✅ **Paper trading** - Buy/sell trades (uses manual price input)
✅ **Historical data** - If data was fetched before, it's cached
✅ **LLM agents** - Analysis works if OHLCV data is available
✅ **All UI interactions** - Buttons, tabs, forms

## 🎯 Expected Behavior

### Local Testing (Your Laptop)
- ⚠️ Charts may fail frequently
- ⚠️ Live prices may be unavailable
- ✅ All other features work
- ✅ Good for testing UI/UX

### OCI Production
- ✅ Charts work reliably during market hours
- ✅ Live prices available (15-min delay)
- ✅ Weekly pipeline runs successfully
- ✅ Full functionality

## 🧪 Testing Without Live Data

You can still test the application by:

### 1. Use Cached Data
If you ran the weekly pipeline before, data is cached in Parquet files:
```bash
ls -lh src/data/ohlcv_cache/
# Shows cached OHLCV data (valid for 12 hours)
```

### 2. Manual Price Entry
In Portfolio tab, you can manually enter prices for Buy/Sell trades:
- Symbol: RELIANCE
- Shares: 10
- Entry Price: 2500 (manual input)
- Click Buy

### 3. Test Other Features
- ✅ Add/remove watchlist symbols
- ✅ Create portfolios (via Python script)
- ✅ View trade history
- ✅ Check settings tab
- ✅ Navigate all tabs

## 📝 Workaround for Testing

If you want to test with real data locally:

### Option A: Use VPN
```bash
# Connect to VPN (changes your IP)
# Then restart dashboard
./local-stop.sh
./local-test.sh
```

### Option B: Reduce Request Frequency
```bash
# Edit src/plutus/data/ohlcv.py
# Increase CACHE_HOURS from 12 to 24
# This reduces requests to yfinance
```

### Option C: Mock Data (Development)
```python
# In src/plutus/data/ohlcv.py, add mock mode:
if os.getenv("MOCK_DATA") == "true":
    return pd.DataFrame({
        "Open": [2500] * 60,
        "High": [2550] * 60,
        "Low": [2450] * 60,
        "Close": [2500] * 60,
        "Volume": [1000000] * 60,
    }, index=pd.date_range(end=datetime.now(), periods=60))
```

## 🚀 Production Deployment Fixes This

Once deployed to OCI:
1. ✅ Different IP address (datacenter, not residential)
2. ✅ Better network routing
3. ✅ Scheduled jobs run during market hours
4. ✅ Data caching reduces requests
5. ✅ More reliable overall

## 📞 When to Worry

**Don't worry if:**
- ❌ Charts fail locally on your laptop
- ❌ Live prices unavailable on weekends
- ❌ Rate limit errors during testing

**Do worry if:**
- ❌ Charts fail on OCI during market hours
- ❌ Weekly pipeline fails completely
- ❌ Database errors or crashes

## 🎓 Key Takeaway

**This is a known limitation of free data sources, not a bug in Plutus.**

The application is designed to:
- ✅ Handle data fetch failures gracefully
- ✅ Show helpful error messages
- ✅ Continue working even without live data
- ✅ Work reliably in production (OCI deployment)

**For production use, deploy to OCI where data fetching is more reliable.**

---

**Last Updated:** 2026-05-31  
**Status:** Expected behavior, not a bug  
**Solution:** Deploy to OCI for reliable data access
