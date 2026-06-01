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
