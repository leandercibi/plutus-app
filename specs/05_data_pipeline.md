# 05 — Data Pipeline

> All data ingestion modules. Implement in order:
> universe → ohlcv → news → reddit → smart_money → trading_calendar.
>
> Code root: `src/plutus/`. Every module path is `plutus.data.*`.
> Every external reference must use `from plutus.config import settings`,
> `from plutus.db.session import SessionLocal`, etc. — the new package layout
> (see `_CHANGE_SPEC.md` §0). No `from config import ...` or `from db.*`.

This document supersedes any earlier draft. The big shifts vs. the original:

- **Universe screener** no longer touches `yfinance.Ticker.info`. It loads a
  checked-in seed CSV (Nifty 500 + MidCap 150) and derives liquidity filters
  from cached OHLCV (`_CHANGE_SPEC.md` §2).
- **News classifier** runs a hard, tiered keyword prefilter from
  `material_keywords.yaml` before any LLM call. Rejected headlines are
  persisted to a `rejected_headlines` table for audit (`_CHANGE_SPEC.md` §5).
- **New helper** `data/trading_calendar.py` provides NSE-aware
  `is_trading_day` / `nse_trading_days_between`, used by the outcome tracker
  (`_CHANGE_SPEC.md` §8).

---

## `data/universe.py` — NSE Stock Universe Screener

### Purpose

Reduce a curated seed list of ~650 NSE symbols (Nifty 500 + MidCap 150) to a
~150–200-symbol tradeable universe using OHLCV-derived liquidity filters
plus an F&O ban exclusion. Runs once per weekly pipeline; cached for the
whole ISO week.

### Logic

1. Load static seed CSV `src/plutus/data/seed_universe.csv`
   (columns: `symbol, exchange, segment`).
2. For each symbol, fetch the last 90 trading days of daily OHLCV via
   `plutus.data.ohlcv.fetch_ohlcv` (already disk-cached, see next module).
3. Compute three filter metrics from OHLCV — no `Ticker.info` calls:
   - `last_close = df["Close"].iloc[-1]`
   - `avg_volume_30d = df["Volume"].tail(30).mean()`
   - `avg_value_30d_cr = (df["Close"] * df["Volume"]).tail(30).mean() / 1e7`
     (₹ Cr; this replaces the old market-cap proxy).
4. Keep symbol iff:
   `UNIVERSE_PRICE_MIN ≤ last_close ≤ UNIVERSE_PRICE_MAX` **and**
   `avg_volume_30d ≥ UNIVERSE_MIN_AVG_VOLUME` **and**
   `avg_value_30d_cr ≥ UNIVERSE_MIN_AVG_VALUE_CR`.
5. F&O ban filter: read `src/plutus/data/fno_ban_list.txt` (one symbol per
   line). If the file is older than 24h, attempt a fresh fetch from NSE; if
   the fetch fails, log a warning and use the stale file.
6. Cache the resulting symbol list to
   `src/plutus/data/.cache/universe_<YYYYWnn>.json` (ISO week tag); reuse
   for the rest of the week.
7. Return `List[str]` of symbols.

`UNIVERSE_MIN_MCAP_CR` and `_fetch_basic_info` (Ticker.info) are **removed**.

```python
# src/plutus/data/universe.py
import json
import logging
import csv
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Set

import requests

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv

logger = logging.getLogger(__name__)

CACHE_DIR = Path("src/plutus/data/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NSE_FNO_BAN_URL = (
    "https://www.nseindia.com/api/liveEquity-derivatives"
    "?index=fno_ban_list_active"
)
FNO_BAN_FILE = Path("src/plutus/data/fno_ban_list.txt")
FNO_BAN_TTL_HOURS = 24


# ── Seed CSV ────────────────────────────────────────────────────────────────

def _load_seed_symbols() -> List[str]:
    path = Path(settings.UNIVERSE_SEED_CSV)
    if not path.exists():
        raise FileNotFoundError(
            f"Seed universe CSV missing at {path}. "
            "Populate it from NSE Nifty 500 + MidCap 150 CSVs."
        )
    symbols: List[str] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                symbols.append(sym)
    # de-dupe but preserve order
    return list(dict.fromkeys(symbols))


# ── F&O ban list ────────────────────────────────────────────────────

def _load_fno_ban_list() -> Set[str]:
    """Refresh ban list from NSE if local file is stale; fall back to stale on error."""
    needs_refresh = (
        not FNO_BAN_FILE.exists()
        or (datetime.utcnow().timestamp() - FNO_BAN_FILE.stat().st_mtime)
        > FNO_BAN_TTL_HOURS * 3600
    )
    if needs_refresh:
        try:
            resp = requests.get(
                NSE_FNO_BAN_URL,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Referer": "https://www.nseindia.com/",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            symbols = sorted({(d.get("symbol") or "").strip().upper() for d in data if d.get("symbol")})
            FNO_BAN_FILE.parent.mkdir(parents=True, exist_ok=True)
            FNO_BAN_FILE.write_text("\n".join(symbols) + "\n")
        except Exception as e:
            logger.warning("F&O ban list refresh failed (%s); using stale file", e)

    if not FNO_BAN_FILE.exists():
        return set()
    return {
        line.strip().upper()
        for line in FNO_BAN_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


# ── Weekly cache ────────────────────────────────────────────────────────────

def _week_tag(d: date | None = None) -> str:
    d = d or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}W{iso_week:02d}"


def _cache_path() -> Path:
    return CACHE_DIR / f"universe_{_week_tag()}.json"


def _load_cached_universe() -> List[str] | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("symbols")
    except Exception:
        return None


def _save_cached_universe(symbols: List[str]) -> None:
    _cache_path().write_text(
        json.dumps({"week": _week_tag(), "symbols": symbols}, indent=2)
    )


# ── Public API ──────────────────────────────────────────────────────────────

def get_universe(use_cache: bool = True) -> List[str]:
    """Return the filtered tradeable universe for the current ISO week."""
    if use_cache:
        cached = _load_cached_universe()
        if cached is not None:
            return cached

    seed = _load_seed_symbols()
    banned = _load_fno_ban_list()

    kept: List[str] = []
    for symbol in seed:
        if symbol in banned:
            continue
        try:
            df = fetch_ohlcv(symbol, days=90, interval="1d")
        except Exception as e:
            logger.debug("OHLCV fetch failed for %s: %s", symbol, e)
            continue
        if df is None or df.empty or len(df) < 30:
            continue

        last_close = float(df["Close"].iloc[-1])
        avg_volume_30d = float(df["Volume"].tail(30).mean())
        avg_value_30d_cr = float((df["Close"] * df["Volume"]).tail(30).mean()) / 1e7

        if not (settings.UNIVERSE_PRICE_MIN <= last_close <= settings.UNIVERSE_PRICE_MAX):
            continue
        if avg_volume_30d < settings.UNIVERSE_MIN_AVG_VOLUME:
            continue
        if avg_value_30d_cr < settings.UNIVERSE_MIN_AVG_VALUE_CR:
            continue

        kept.append(symbol)

    _save_cached_universe(kept)
    logger.info(
        "Universe built: %d / %d seed symbols passed filters (week %s)",
        len(kept), len(seed), _week_tag(),
    )
    return kept


def get_watchlist_symbols() -> List[str]:
    from plutus.db.session import SessionLocal
    from plutus.db.models import Watchlist
    with SessionLocal() as db:
        return [w.symbol for w in db.query(Watchlist).all()]


def get_full_analysis_set() -> List[str]:
    """Universe ∪ watchlist — watchlist symbols always pass through."""
    return list(dict.fromkeys(get_universe() + get_watchlist_symbols()))
```

### `seed_universe.csv` format

Checked-in at `src/plutus/data/seed_universe.csv`. Refresh manually each
month from NSE indices:

- Nifty 500: <https://www.nseindia.com/products-services/indices-nifty500-index>
- Nifty MidCap 150: <https://www.nseindia.com/products-services/indices-nifty-midcap-150-index>

Use the helper `scripts/refresh_seed_universe.py` (manual run) to merge the
two NSE CSVs and dedupe. The committed CSV is the runtime source of truth.

```csv
symbol,exchange,segment
RELIANCE,NSE,LARGE_CAP
TCS,NSE,LARGE_CAP
HDFCBANK,NSE,LARGE_CAP
PERSISTENT,NSE,MID_CAP
TRENT,NSE,MID_CAP
```

`segment` is informational only (`LARGE_CAP` for Nifty 500 constituents,
`MID_CAP` for Nifty MidCap 150 additions). Universe filtering is purely
OHLCV-driven.

---

## `data/ohlcv.py` — OHLCV Data Fetcher

### Purpose

Fetch historical candlestick data and live LTP for any NSE/BSE symbol.
Source: yfinance (free, ~15-min delay during market hours, settled by 5pm IST after close). Sufficient for swing-trade horizons; no real-time feed needed.

### Intervals Supported

- `"1d"` — daily candles (default; used by universe + bundles + outcome tracker)
- `"1h"` — hourly (intraday strategy context)
- `"15m"` — 15-minute (Opening Range strategy)
- `"5m"` — 5-minute (entry refinement)

### Cache

Daily-interval calls are cached on disk as Parquet at
`src/plutus/data/.cache/ohlcv_<symbol>_<days>.parquet` with a 12-hour TTL.
This is the cache the universe screener and bundle runners share — one
yfinance fetch per symbol per half-day.

```python
# src/plutus/data/ohlcv.py
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from plutus.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path("src/plutus/data/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OHLCV_CACHE_TTL_HOURS = 12


def _nse_symbol(symbol: str, exchange: str = "NSE") -> str:
    suffix = ".NS" if exchange == "NSE" else ".BO"
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}{suffix}"


def _cache_path(symbol: str, days: int) -> Path:
    return CACHE_DIR / f"ohlcv_{symbol.upper()}_{days}.parquet"


def _read_cache(symbol: str, days: int) -> pd.DataFrame | None:
    p = _cache_path(symbol, days)
    if not p.exists():
        return None
    age_h = (datetime.utcnow().timestamp() - p.stat().st_mtime) / 3600
    if age_h > OHLCV_CACHE_TTL_HOURS:
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _write_cache(symbol: str, days: int, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_cache_path(symbol, days))
    except Exception as e:
        logger.debug("Parquet cache write failed for %s: %s", symbol, e)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_ohlcv(
    symbol: str,
    days: int = 90,
    interval: str = "1d",
    exchange: str = "NSE",
) -> pd.DataFrame:
    """
    Returns DataFrame with columns: Open, High, Low, Close, Volume.
    Index: DatetimeIndex (timezone-naive).

    Daily-interval calls are disk-cached as Parquet for 12h.
    """
    if interval == "1d":
        cached = _read_cache(symbol, days)
        if cached is not None:
            return cached

    ticker_sym = _nse_symbol(symbol, exchange)
    end = datetime.now()
    start = end - timedelta(days=days + 10)  # buffer for weekends/holidays
    df = yf.download(
        ticker_sym,
        start=start,
        end=end,
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        raise ValueError(f"No data returned for {ticker_sym}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.tail(days)

    if interval == "1d":
        _write_cache(symbol, days, df)
    return df


def fetch_live_price(symbol: str, exchange: str = "NSE") -> float:
    """Returns current market price (or last close if market is closed). ~15-min delayed via yfinance."""
    ticker = yf.Ticker(_nse_symbol(symbol, exchange))
    info = ticker.fast_info
    return info.last_price or info.previous_close


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all technical indicators using pandas-ta.
    Called by strategy bundles and the technical agent.
    Returns the same DataFrame with additional columns.
    """
    import pandas_ta_classic as ta  # the maintained PyPI fork; module name differs from the original `pandas_ta`

    df.ta.ema(length=9, append=True)
    df.ta.ema(length=21, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.bbands(length=20, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.stoch(append=True)
    df.ta.adx(append=True)
    df.ta.obv(append=True)

    df["Volume_MA20"] = df["Volume"].rolling(20).mean()
    df["Volume_Ratio"] = df["Volume"] / df["Volume_MA20"]

    df["Body_Size"] = abs(df["Close"] - df["Open"])
    df["Upper_Wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
    df["Lower_Wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]

    return df.dropna(subset=["EMA_9", "RSI_14"])


```

---

## `data/news.py` — News Fetcher + Tiered Prefilter + Batch Classifier

### Sources

1. **Economic Times RSS** — free
2. **MoneyControl RSS** — free
3. **Business Standard RSS** — free
4. **LiveMint RSS** — free
5. **NewsAPI** — optional, free tier (100 req/day) if `NEWS_API_KEY` set

### Algorithm

For each symbol the news monitor cares about (watchlist ∪ open positions):

1. `fetch_news(symbol)` pulls raw headlines from RSS (and NewsAPI if keyed).
2. `prefilter_headlines(headlines)` runs a **hard substring match** against
   the keyword YAML:
   - Hit on **stoplist** → reject (`filter_status="stoplist"`).
   - Else hit on any enabled-tier keyword → keep (`filter_status="kept"`).
   - Else → reject (`filter_status="no_keyword"`).
3. Rejected headlines are persisted to the `rejected_headlines` table for
   audit (powers the dashboard "Rejected Headlines (last 7d)" panel).
4. If **no** headlines survive the prefilter, the function returns a neutral
   payload **without calling the LLM**. Cost guard.
5. Otherwise, a **single batched LLM call** classifies all kept headlines
   for that symbol (one call per symbol, capped at 15 headlines).

This is the cost discipline mandated by `_CHANGE_SPEC.md` §5 and §7. Default
LLM model is `settings.DEEPSEEK_FAST_MODEL` (V4 Flash for both fast and
synthesizer, see §7).

### Full module

```python
# src/plutus/data/news.py
import json
import yaml
import feedparser
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict
from plutus.config import settings
from plutus.db.session import SessionLocal
from plutus.db.models import RejectedHeadline


RSS_FEEDS = {
    "economic_times": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "moneycontrol": "https://www.moneycontrol.com/rss/marketoutlook.xml",
    "business_standard": "https://www.business-standard.com/rss/markets-106.rss",
    "livemint": "https://www.livemint.com/rss/markets",
}


_KEYWORDS_CACHE = None
_STOPLIST_CACHE = None


def _load_keywords():
    """Lazy-load keywords from yaml; returns (keywords_set, stoplist_set)."""
    global _KEYWORDS_CACHE, _STOPLIST_CACHE
    if _KEYWORDS_CACHE is not None:
        return _KEYWORDS_CACHE, _STOPLIST_CACHE
    path = Path(settings.MATERIAL_KEYWORDS_YAML)
    data = yaml.safe_load(path.read_text())
    enabled_tiers = [t.strip() for t in settings.MATERIAL_KEYWORD_TIERS.split(",")]
    kws = []
    for tier in enabled_tiers:
        kws.extend(data.get(f"tier_{tier}", []))
    _KEYWORDS_CACHE = set(k.lower() for k in kws)
    _STOPLIST_CACHE = set(s.lower() for s in data.get("stoplist", []))
    return _KEYWORDS_CACHE, _STOPLIST_CACHE


def fetch_news(symbol: str, hours: int = 48) -> List[Dict]:
    """Fetch raw headlines for a symbol from all RSS feeds (and NewsAPI if keyed)."""
    results: List[Dict] = []
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    if settings.NEWS_API_KEY:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f"{symbol} stock NSE",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                    "pageSize": 20,
                    "apiKey": settings.NEWS_API_KEY,
                },
                timeout=10,
            )
            for article in resp.json().get("articles", []):
                results.append({
                    "headline": article["title"],
                    "source": article["source"]["name"],
                    "published_at": article["publishedAt"],
                    "url": article["url"],
                })
        except Exception:
            pass

    for source, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                headline = entry.get("title", "")
                if symbol.lower() in headline.lower():
                    results.append({
                        "headline": headline,
                        "source": source,
                        "published_at": entry.get("published", ""),
                        "url": entry.get("link", ""),
                    })
        except Exception:
            continue

    return results


def prefilter_headlines(headlines: List[Dict]) -> tuple[List[Dict], List[Dict]]:
    """
    Returns (kept, rejected) where each item has filter_status set.
    kept: matched a keyword (and not stoplist)
    rejected: matched stoplist OR matched no keyword
    """
    keywords, stoplist = _load_keywords()
    kept, rejected = [], []
    for h in headlines:
        title = h["headline"].lower()
        if any(s in title for s in stoplist):
            h["filter_status"] = "stoplist"
            rejected.append(h)
        elif any(k in title for k in keywords):
            h["filter_status"] = "kept"
            kept.append(h)
        else:
            h["filter_status"] = "no_keyword"
            rejected.append(h)
    return kept, rejected


def save_rejected_headlines(symbol: str, rejected: List[Dict]):
    """Persist rejected headlines for audit."""
    if not rejected:
        return
    with SessionLocal() as db:
        for h in rejected:
            db.add(RejectedHeadline(
                symbol=symbol,
                headline=h["headline"],
                source=h.get("source"),
                published_at=h.get("published_at"),
                filter_status=h["filter_status"],
            ))
        db.commit()


def classify_news(symbol: str, headlines: List[Dict]) -> Dict:
    """Hard prefilter then single batched LLM call. No prefilter passes -> no LLM call."""
    if not headlines:
        return {"sentiment_score": 0, "sentiment_label": "neutral",
                "is_material": False, "material_event_type": None,
                "summary": "No recent news found."}

    kept, rejected = prefilter_headlines(headlines)
    save_rejected_headlines(symbol, rejected)

    if not kept:
        return {"sentiment_score": 0, "sentiment_label": "neutral",
                "is_material": False, "material_event_type": None,
                "summary": f"No material headlines (filtered {len(rejected)})."}

    return _llm_batch_classify(symbol, kept)


def _llm_batch_classify(symbol: str, kept: List[Dict]) -> Dict:
    from plutus.agents.openrouter_client import call_llm
    from plutus.agents.prompts import NEWS_CLASSIFIER_PROMPT
    headlines_text = "\n".join(f"- {h['headline']} ({h['source']})" for h in kept[:15])
    user_msg = f"Stock: {symbol}\nHeadlines:\n{headlines_text}"
    response = call_llm([
        {"role": "system", "content": NEWS_CLASSIFIER_PROMPT},
        {"role": "user", "content": user_msg},
    ], model=settings.DEEPSEEK_FAST_MODEL, response_format="json")
    try:
        result = json.loads(response)
        return {
            "sentiment_score": result.get("sentiment_score", 0),
            "sentiment_label": result.get("sentiment_label", "neutral"),
            "is_material": bool(result.get("is_material", False)),
            "material_event_type": result.get("material_event_type"),
            "summary": result.get("summary", ""),
        }
    except Exception:
        return {"sentiment_score": 0, "sentiment_label": "neutral",
                "is_material": False, "material_event_type": None,
                "summary": "Classification failed."}
```

### `material_keywords.yaml` format

Checked-in at `src/plutus/data/material_keywords.yaml`. Three tiers
(`tier_A`, `tier_B`, `tier_C`) plus a `stoplist`. All matches are
**case-insensitive substring** matches. Stoplist hits override tier hits
and reject the headline.

The file ships with all three tiers fully populated; tier C is present in
the YAML but **disabled by default**. Which tiers are active is controlled
by `settings.MATERIAL_KEYWORD_TIERS` (default `"A,B"`). See
`_CHANGE_SPEC.md` §5 for the seed keyword set — copy that block verbatim
into the YAML on first checkout.

```yaml
# src/plutus/data/material_keywords.yaml
# Plutus material-event keyword prefilter
# All matches are case-insensitive substring matches.
# Hits in ANY enabled tier → headline is sent to LLM classifier.
# Stoplist matches override tier matches and reject the headline.

tier_A:
  - sebi
  - usfda
  - quarterly result
  - acquisition
  # … see _CHANGE_SPEC.md §5 for the full seed list

tier_B:
  - block deal
  - promoter pledge
  - rating downgrade
  # … full list in _CHANGE_SPEC.md §5

tier_C:
  - buyback
  - bonus issue
  - upper circuit
  # … full list in _CHANGE_SPEC.md §5; disabled by default

stoplist:
  - "top 5"
  - "top 10"
  - "stocks to buy"
  - "multibagger"
  # … full list in _CHANGE_SPEC.md §5
```

To enable tier C in production, set `MATERIAL_KEYWORD_TIERS=A,B,C` in
`.env` and restart `plutus-main.service`. The keyword cache is
process-local; restarts pick up YAML edits.

The `rejected_headlines` table (see `04_database.md`) is the audit trail.
The dashboard "News Feed → Rejected Headlines (last 7d)" tab reads from it
and offers a copy-paste "Promote keyword" hint that suggests the YAML edit
the user should make manually.

---

## `data/reddit.py` — Reddit Sentiment

Module path: `plutus.data.reddit`. Shape unchanged from the previous draft;
imports updated to the new package layout.

```python
# src/plutus/data/reddit.py
import praw
from typing import Dict
from datetime import datetime, timedelta
from plutus.config import settings

SUBREDDITS = ["IndianStreetBets", "IndiaInvestments", "Zerodha", "stocks"]


def get_reddit_client():
    return praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )


def get_reddit_sentiment(symbol: str, days: int = 7) -> Dict:
    """
    Returns mention count + sentiment estimate for a stock.
    Falls back gracefully if Reddit is not configured.
    """
    if not settings.REDDIT_ENABLED:
        return {"mentions": 0, "sentiment": "neutral", "posts": []}

    reddit = get_reddit_client()
    cutoff = datetime.utcnow() - timedelta(days=days)
    mentions = []

    for subreddit_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.search(symbol, time_filter="week", limit=20):
                if datetime.utcfromtimestamp(post.created_utc) > cutoff:
                    mentions.append({
                        "title": post.title,
                        "score": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "subreddit": subreddit_name,
                    })
        except Exception:
            continue

    if not mentions:
        return {"mentions": 0, "sentiment": "neutral", "posts": []}

    avg_ratio = sum(m["upvote_ratio"] for m in mentions) / len(mentions)
    high_engagement = [m for m in mentions if m["num_comments"] > 10]

    if avg_ratio > 0.75 and len(high_engagement) > 2:
        sentiment = "positive"
    elif avg_ratio < 0.45:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "mentions": len(mentions),
        "sentiment": sentiment,
        "avg_upvote_ratio": round(avg_ratio, 2),
        "high_engagement_posts": len(high_engagement),
        "posts": mentions[:5],
    }
```

---

## `data/smart_money.py` — MF + FII/DII Data

Module path: `plutus.data.smart_money`. Shape unchanged; imports updated.

```python
# src/plutus/data/smart_money.py
from mftool import Mftool
import requests
from typing import Dict, List
from datetime import date


def get_mf_signal(symbol: str) -> Dict:
    """
    Checks if mutual funds are accumulating or reducing holdings.
    Data: AMFI monthly portfolio disclosures (45-day lag).
    Returns: {verdict, mf_count_accumulating, mf_count_reducing, details}
    """
    try:
        Mftool()  # ensure import path works; stock-level lookup is custom
        return _scrape_nse_mf_holdings(symbol)
    except Exception:
        return {"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0}


def _scrape_nse_mf_holdings(symbol: str) -> Dict:
    """
    Scrapes NSE/AMFI for mutual fund holdings change.
    NSE provides MF aggregate data at:
    https://www.nseindia.com/api/mutual-funds-equity-report
    """
    try:
        url = f"https://api.tickertape.in/stocks/{symbol}/holders"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            return {
                "verdict": "UNKNOWN",
                "mf_count_accumulating": 0,
                "mf_count_reducing": 0,
                "details": [],
            }
    except Exception:
        pass
    return {"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0}


def get_fii_dii_flow() -> Dict:
    """
    Gets FII and DII net buy/sell for today from NSE.
    https://www.nseindia.com/api/fiidiiTradeReact
    Returns: {fii_net_cr, dii_net_cr, fii_signal, dii_signal, date}
    """
    try:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        latest = data[0] if data else {}
        fii_net = float(latest.get("fii_net_buy_sell", 0))
        dii_net = float(latest.get("dii_net_buy_sell", 0))
        return {
            "fii_net_cr": round(fii_net / 1e7, 2),
            "dii_net_cr": round(dii_net / 1e7, 2),
            "fii_signal": "net_buyer" if fii_net > 0 else "net_seller",
            "dii_signal": "net_buyer" if dii_net > 0 else "net_seller",
            "date": latest.get("date", str(date.today())),
        }
    except Exception:
        return {
            "fii_net_cr": 0,
            "dii_net_cr": 0,
            "fii_signal": "unknown",
            "dii_signal": "unknown",
            "date": str(date.today()),
        }


def get_bulk_deals(symbol: str) -> List[Dict]:
    """Fetches bulk/block deals from NSE for a given symbol."""
    try:
        url = "https://www.nseindia.com/api/block-deal"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        resp = requests.get(url, headers=headers, timeout=10)
        deals = resp.json().get("data", [])
        return [d for d in deals if d.get("symbol", "").upper() == symbol.upper()]
    except Exception:
        return []
```

---

## `data/trading_calendar.py` — NSE Trading-Day Helper (NEW)

### Purpose

The outcome tracker (`_CHANGE_SPEC.md` §8) and Monday re-validation job
need to count **NSE trading days** between two IST dates, not raw weekdays.
This module loads a checked-in static holiday list and exposes two helpers.

### Behaviour

- `is_trading_day(d)`: weekday and not in the holiday set.
- `nse_trading_days_between(start, end)`: count of trading days in
  `(start, end]` — strictly **after** `start`, up to and including `end`.
  Returns 0 if `end <= start`.
- If `NSE_HOLIDAYS_FILE` is missing, the cache is an empty set and the
  helpers degrade to "weekdays only" (a logged warning is the caller's
  responsibility — see outcome tracker).

```python
# src/plutus/data/trading_calendar.py
from pathlib import Path
from datetime import date, timedelta
from plutus.config import settings


_HOLIDAYS_CACHE = None

def _load_holidays() -> set[date]:
    global _HOLIDAYS_CACHE
    if _HOLIDAYS_CACHE is not None:
        return _HOLIDAYS_CACHE
    p = Path(settings.NSE_HOLIDAYS_FILE)
    if not p.exists():
        _HOLIDAYS_CACHE = set()
        return _HOLIDAYS_CACHE
    _HOLIDAYS_CACHE = {date.fromisoformat(line.strip())
                       for line in p.read_text().splitlines()
                       if line.strip() and not line.startswith("#")}
    return _HOLIDAYS_CACHE


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _load_holidays()


def nse_trading_days_between(start: date, end: date) -> int:
    """Count NSE trading days strictly between start (exclusive) and end (inclusive)."""
    if end <= start:
        return 0
    days = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            days += 1
        cur += timedelta(days=1)
    return days
```

### `nse_holidays.txt` seed

Checked-in at `src/plutus/data/nse_holidays.txt`. One ISO date per line.
`#`-prefixed lines and blank lines are ignored. Refresh **yearly** from
the official NSE trading-holiday calendar at
<https://www.nseindia.com/resources/exchange-communication-holidays>.

Seed content (2026 — verify against the official NSE calendar before each
calendar year and update). The loader above accepts only pure ISO dates on
data lines; everything starting with `#` (or a blank line) is skipped, so
holiday names live in `#` comments above each entry, **not** inline.

```text
# NSE trading holidays — one ISO date per line.
# Update yearly from https://www.nseindia.com/resources/exchange-communication-holidays
# Lines beginning with '#' are comments and ignored.
#
# 2026 — provisional seed; reconcile with the official NSE notice each January.
# Republic Day
2026-01-26
# Holi
2026-03-04
# Good Friday
2026-04-03
# Dr. B.R. Ambedkar Jayanti
2026-04-14
# Maharashtra Day
2026-05-01
# Independence Day
2026-08-15
# Ganesh Chaturthi
2026-08-26
# Mahatma Gandhi Jayanti
2026-10-02
# Diwali (Laxmi Pujan) — confirm muhurat session timing separately
2026-10-21
# Diwali Balipratipada
2026-10-22
# Guru Nanak Jayanti
2026-11-24
# Christmas
2026-12-25
```

---

## Data Flow Summary

```
Weekly Pipeline Sunday 18:00 IST:
  get_universe()                    → ~150-200 symbols
       ↓ (seed CSV → fetch_ohlcv → liquidity filter → F&O ban → week cache)
  fetch_ohlcv(each, 90d) × N        → DataFrames (12h Parquet cache hits free)
       ↓
  add_indicators(each)              → DataFrames with 15+ indicator columns
       ↓
  run_all_bundles(each)             → 5 bundles per symbol (Trend, Reversal,
                                       Breakout, SMC, Composite)
       ↓
  Top 20 by composite score
       ↓
  For each of top 20:
    fetch_news(symbol)              → raw headlines
    classify_news(symbol, ...)      → prefilter → batch LLM (≤1 call/symbol)
    get_reddit_sentiment(symbol)
    get_mf_signal(symbol)
    get_fii_dii_flow()              → once per run, not per symbol
       ↓
  run_analysis(symbol)              → LangGraph agent pipeline
       ↓
  Save to DB + write reports/weekly/<date>.md

Monday 09:10 IST re-validation:
  fetch_live_price(symbol) for each pending BUY/WATCH from latest run
       ↓
  Pure price math: gap > +2% downgrades BUY→WATCH; LTP < stop downgrades →AVOID
       ↓
  Single Telegram delta message. No LLM calls.

Outcome tracker (Mon-Fri 16:30 IST):
  For each PENDING recommendation older than hold_days_min trading days:
    nse_trading_days_between(created_ist, today_ist)  ← trading_calendar
    fetch_ohlcv(symbol, days=elapsed+5)
    walk forward → HIT_T1 / HIT_T2 / STOPPED / EXPIRED (stop wins ties)

On-Demand (any time):
  fetch_ohlcv(symbol, days=90)      → ~3s cold, free on cache hit
  add_indicators()                  → <1s
  run_all_bundles(symbol)           → ~3s (single stock)
  fetch_news() + reddit()           → ~2s
  run_analysis()                    → 10-15s (LLM calls)
```

---

## Verification

Quick smoke checks after implementing this module group. Run from repo
root with the venv active.

```bash
# Universe loads from seed CSV and produces a non-empty list (assumes seed
# CSV is populated and yfinance is reachable).
python -c "from plutus.data.universe import get_universe; u = get_universe(); print(len(u), u[:5])"

# OHLCV fetch + cache round-trip.
python -c "
from plutus.data.ohlcv import fetch_ohlcv
df = fetch_ohlcv('RELIANCE', days=90)
print(df.tail(3))
print('cached:', (__import__('pathlib').Path('src/plutus/data/.cache/ohlcv_RELIANCE_90.parquet').exists()))
"

# News prefilter sanity — should reject a stoplist headline and keep an SEBI one.
python -c "
from plutus.data.news import prefilter_headlines
kept, rej = prefilter_headlines([
    {'headline': 'Top 5 stocks to buy this week', 'source': 'x'},
    {'headline': 'SEBI bars firm from market access', 'source': 'x'},
    {'headline': 'Random unrelated headline', 'source': 'x'},
])
print('kept:', [h['headline'] for h in kept])
print('rejected:', [(h['headline'], h['filter_status']) for h in rej])
"

# Trading calendar — count trading days between two dates.
python -c "
from datetime import date
from plutus.data.trading_calendar import nse_trading_days_between, is_trading_day
print(is_trading_day(date(2026,1,26)))           # False — Republic Day
print(nse_trading_days_between(date(2026,1,1), date(2026,1,31)))
"

# F&O ban file refresh path exists (manual: delete to force re-fetch).
ls -la src/plutus/data/fno_ban_list.txt || echo "missing — will be created on first universe build"
```
