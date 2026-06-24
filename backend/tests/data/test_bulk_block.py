from __future__ import annotations

from datetime import date
from decimal import Decimal

from plutus.data.bulk_block import BulkBlockEvent, fetch_bulk_block


class _StubBulkBlock:
    def __init__(self, events: dict[str, list[BulkBlockEvent]]) -> None:
        self._events = events

    def fetch(self, symbol: str, start: date, end: date) -> list[BulkBlockEvent]:
        return [e for e in self._events.get(symbol, []) if start <= e.date <= end]


def _provider() -> _StubBulkBlock:
    events = {
        "INFY": [
            BulkBlockEvent(
                symbol="INFY",
                date=date(2025, 1, 5),
                qty=10_000,
                value_inr=Decimal("15000000"),
                buyer="FII-A",
                seller="DII-B",
            ),
            BulkBlockEvent(
                symbol="INFY",
                date=date(2025, 1, 20),
                qty=5_000,
                value_inr=Decimal("7500000"),
                buyer="MF-C",
                seller="INDIVIDUAL",
            ),
        ]
    }
    return _StubBulkBlock(events)


def test_schema_fields_present() -> None:
    events = fetch_bulk_block("INFY", date(2025, 1, 1), date(2025, 1, 31), _provider())
    e = events[0]
    assert e.symbol == "INFY"
    assert e.qty == 10_000
    assert e.value_inr == Decimal("15000000")
    assert e.buyer == "FII-A"


def test_date_filtering() -> None:
    events = fetch_bulk_block("INFY", date(2025, 1, 1), date(2025, 1, 10), _provider())
    assert len(events) == 1
    assert events[0].date == date(2025, 1, 5)


def test_unknown_symbol_returns_empty() -> None:
    events = fetch_bulk_block(
        "UNKNOWN", date(2025, 1, 1), date(2025, 1, 31), _provider()
    )
    assert events == []


def test_qty_value_sanity() -> None:
    events = fetch_bulk_block("INFY", date(2025, 1, 1), date(2025, 1, 31), _provider())
    for e in events:
        assert e.qty > 0
        assert e.value_inr > 0
