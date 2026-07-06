"""Marketaux financial-news provider.

Fetches recent news + per-entity sentiment for a set of NSE tickers in a single
request, so the AI weekly summary can add a "News watch" angle on the stocks in
the signals list. Free tier: ~100 requests/day, max 3 articles per request —
because summaries are cached per pipeline run, we make roughly one request per
run, staying comfortably inside those limits.

Everything degrades gracefully: no key, a network error, or zero coverage all
return an empty list rather than raising, so the summary simply omits news.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from plutus.config.settings import Settings

logger = logging.getLogger(__name__)

# Yahoo-style exchange suffixes Marketaux uses; stripped to recover our symbol.
_KNOWN_SUFFIXES = (".NS", ".BO", ".NSE", ".BSE")


@dataclass
class NewsItem:
    symbol: str
    title: str
    snippet: str
    url: str
    source: str
    published_at: str
    sentiment_score: float | None  # -1..1 per Marketaux entity, when present
    sector: str | None = None  # Marketaux industry, set on sector-based fetches


@dataclass
class MarketauxProvider:
    api_key: str
    base_url: str = "https://api.marketaux.com/v1"
    symbol_suffix: str = ".NS"
    timeout_seconds: int = 20

    def _to_market_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s.endswith(_KNOWN_SUFFIXES):
            return s
        return f"{s}{self.symbol_suffix}"

    @staticmethod
    def _strip_suffix(market_symbol: str) -> str:
        s = market_symbol.strip().upper()
        for suf in _KNOWN_SUFFIXES:
            if s.endswith(suf):
                return s[: -len(suf)]
        return s

    def fetch_for_symbols(
        self, symbols: list[str], limit: int = 3, lookback_days: int = 7
    ) -> list[NewsItem]:
        """Return news items tagged to the requested symbols. Never raises."""
        wanted = {s.strip().upper() for s in symbols if s.strip()}
        if not wanted:
            return []

        params: dict[str, str | int] = {
            "symbols": ",".join(self._to_market_symbol(s) for s in sorted(wanted)),
            "filter_entities": "true",
            "language": "en",
            "limit": limit,
            "api_token": self.api_key,
        }
        if lookback_days:
            after = datetime.utcnow() - timedelta(days=lookback_days)
            params["published_after"] = after.strftime("%Y-%m-%dT%H:%M")

        try:
            resp = requests.get(
                f"{self.base_url.rstrip('/')}/news/all",
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.warning("marketaux request failed: %s", exc)
            return []

        if resp.status_code != 200:
            logger.warning("marketaux returned %s: %s", resp.status_code, resp.text[:200])
            return []

        try:
            articles = resp.json().get("data", [])
        except ValueError:
            logger.warning("marketaux returned non-JSON body")
            return []

        items: list[NewsItem] = []
        for art in articles:
            title = (art.get("title") or "").strip()
            snippet = (art.get("description") or art.get("snippet") or "").strip()
            url = art.get("url") or ""
            source = art.get("source") or ""
            published = art.get("published_at") or ""
            for ent in art.get("entities", []):
                ent_sym = self._strip_suffix(ent.get("symbol") or "")
                if ent_sym in wanted:
                    items.append(
                        NewsItem(
                            symbol=ent_sym,
                            title=title,
                            snippet=snippet[:280],
                            url=url,
                            source=source,
                            published_at=published,
                            sentiment_score=ent.get("sentiment_score"),
                        )
                    )
        return items

    def resolve_industry(self, symbol: str) -> str | None:
        """Look up a symbol's sector (Marketaux industry taxonomy). None on miss."""
        market_sym = self._to_market_symbol(symbol)
        try:
            resp = requests.get(
                f"{self.base_url.rstrip('/')}/entity/search",
                params={"search": market_sym, "api_token": self.api_key},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.warning("marketaux entity search failed for %s: %s", symbol, exc)
            return None
        if resp.status_code != 200:
            logger.warning("marketaux entity search %s -> %s", symbol, resp.status_code)
            return None
        try:
            data = resp.json().get("data", [])
        except ValueError:
            return None

        want = symbol.strip().upper()
        best = next(
            (e for e in data if self._strip_suffix(e.get("symbol") or "") == want),
            data[0] if data else None,
        )
        if best is None:
            return None
        return (best.get("industry") or "").strip() or None

    def fetch_by_industry(
        self, industry: str, limit: int = 3, lookback_days: int = 14, country: str = "in"
    ) -> list[NewsItem]:
        """Return recent news for a sector (industry), tagged with that sector."""
        params: dict[str, str | int] = {
            "industries": industry,
            "filter_entities": "true",
            "language": "en",
            "limit": limit,
            "api_token": self.api_key,
        }
        if country:
            params["countries"] = country
        if lookback_days:
            after = datetime.utcnow() - timedelta(days=lookback_days)
            params["published_after"] = after.strftime("%Y-%m-%dT%H:%M")

        try:
            resp = requests.get(
                f"{self.base_url.rstrip('/')}/news/all", params=params, timeout=self.timeout_seconds
            )
        except requests.RequestException as exc:
            logger.warning("marketaux industry fetch failed (%s): %s", industry, exc)
            return []
        if resp.status_code != 200:
            logger.warning(
                "marketaux industry %s -> %s: %s", industry, resp.status_code, resp.text[:200]
            )
            return []
        try:
            articles = resp.json().get("data", [])
        except ValueError:
            return []

        items: list[NewsItem] = []
        for art in articles:
            entities = art.get("entities", [])
            rep = next((e for e in entities if (e.get("industry") or "") == industry), None)
            if rep is None and entities:
                rep = entities[0]
            items.append(
                NewsItem(
                    symbol=self._strip_suffix(rep.get("symbol") or "") if rep else "",
                    title=(art.get("title") or "").strip(),
                    snippet=(art.get("description") or art.get("snippet") or "").strip()[:280],
                    url=art.get("url") or "",
                    source=art.get("source") or "",
                    published_at=art.get("published_at") or "",
                    sentiment_score=rep.get("sentiment_score") if rep else None,
                    sector=industry,
                )
            )
        return items


def build_news_provider(settings: Settings) -> MarketauxProvider | None:
    """Return a configured provider, or None when no API key is set."""
    if settings.marketaux_api_key is None:
        return None
    return MarketauxProvider(
        api_key=settings.marketaux_api_key.get_secret_value(),
        base_url=settings.marketaux_base_url,
        symbol_suffix=settings.marketaux_symbol_suffix,
        timeout_seconds=settings.news_timeout_seconds,
    )
