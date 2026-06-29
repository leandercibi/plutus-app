from __future__ import annotations

from datetime import date
from decimal import Decimal

from plutus.alerts.formatter import AlertFormatter
from plutus.alerts.whatsapp import build_whatsapp_channel
from plutus.config.settings import Settings


def test_entry_message_has_all_fields() -> None:
    fmt = AlertFormatter()
    msg = fmt.format_entry(
        "INFY", Decimal("100"), Decimal("95"), Decimal("110"), date(2025, 1, 1)
    )
    assert msg.symbol == "INFY"
    assert "*INFY*" in msg.body_md
    assert msg.deduplication_key == "INFY:ENTRY:2025-01-01"


def test_regime_flip_includes_both_labels() -> None:
    fmt = AlertFormatter()
    msg = fmt.format_regime_flip("BULL", "BEAR", date(2025, 1, 1))
    assert "BULL" in msg.body_md
    assert "BEAR" in msg.body_md


def test_whatsapp_disabled_without_key() -> None:
    assert build_whatsapp_channel(Settings(_env_file=None)) is None


def test_whatsapp_enabled_with_key() -> None:
    s = Settings(_env_file=None, whatsapp_api_key="secret-key")
    ch = build_whatsapp_channel(s)
    assert ch is not None
    assert ch.name == "whatsapp"
