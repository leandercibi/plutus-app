from __future__ import annotations

from datetime import datetime

from plutus.data.news import Headline, fetch_headlines


class _StubNews:
    def __init__(self, mapping: dict[str, list[dict]]) -> None:
        self._mapping = mapping

    def fetch(self, symbol: str, lookback_hours: int) -> list[dict]:
        return list(self._mapping.get(symbol, []))


def _raw(url: str, title: str, source: str = "moneycontrol") -> dict:
    return {
        "url": url,
        "source": source,
        "published_at": datetime(2025, 1, 1, 9, 0),
        "title": title,
        "body": title + " full body text",
    }


def test_headlines_returned_as_dataclasses() -> None:
    provider = _StubNews({"INFY": [_raw("u1", "Infosys wins large deal")]})
    out = fetch_headlines("INFY", provider=provider)
    assert len(out) == 1
    assert isinstance(out[0], Headline)
    assert out[0].title == "Infosys wins large deal"


def test_dedup_by_url() -> None:
    provider = _StubNews(
        {
            "INFY": [
                _raw("same-url", "Headline A"),
                _raw("same-url", "Headline A duplicate"),
                _raw("other-url", "Headline B"),
            ]
        }
    )
    out = fetch_headlines("INFY", provider=provider)
    assert len(out) == 2


def test_unknown_symbol_returns_empty() -> None:
    provider = _StubNews({})
    assert fetch_headlines("UNKNOWN", provider=provider) == []


def test_entities_populated_by_deterministic_ner() -> None:
    provider = _StubNews({"INFY": [_raw("u1", "Infosys and TCS sign pact")]})
    out = fetch_headlines("INFY", provider=provider, symbol_aliases={"INFY": ["Infosys"]})
    assert "Infosys" in out[0].entities
