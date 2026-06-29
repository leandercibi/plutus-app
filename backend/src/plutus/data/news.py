from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast


@dataclass(frozen=True)
class Headline:
    source: str
    published_at: datetime
    title: str
    body: str
    url: str
    entities: list[str]


class NewsProvider(Protocol):
    def fetch(self, symbol: str, lookback_hours: int) -> list[dict[str, object]]: ...


def _extract_entities(text: str, aliases: list[str]) -> list[str]:
    """Deterministic NER stub: exact substring match of known aliases.

    No LLM involvement (11_ / 00_principles §4) — purely lexical.
    """
    found: list[str] = []
    for alias in aliases:
        if alias and alias in text and alias not in found:
            found.append(alias)
    return found


def fetch_headlines(
    symbol: str,
    provider: NewsProvider,
    lookback_hours: int = 168,
    symbol_aliases: dict[str, list[str]] | None = None,
) -> list[Headline]:
    """Return de-duplicated (by URL) headlines as text. Unknown symbol -> empty list."""
    raw = provider.fetch(symbol, lookback_hours)
    aliases = (symbol_aliases or {}).get(symbol, [])

    seen_urls: set[str] = set()
    out: list[Headline] = []
    for item in raw:
        url = cast(str, item["url"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = cast(str, item["title"])
        body = cast(str, item.get("body", ""))
        text = f"{title} {body}"
        out.append(
            Headline(
                source=cast(str, item["source"]),
                published_at=cast(datetime, item["published_at"]),
                title=title,
                body=body,
                url=url,
                entities=_extract_entities(text, aliases),
            )
        )
    return out
