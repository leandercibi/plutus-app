from __future__ import annotations

from datetime import date
from decimal import Decimal

from plutus.alerts.channels import AlertMessage


class AlertFormatter:
    """Message templates. Each method returns a fully-populated AlertMessage with a
    deterministic deduplication key."""

    def format_entry(
        self, symbol: str, entry: Decimal, stop: Decimal, t1: Decimal, on: date
    ) -> AlertMessage:
        body = f"Entry {entry} | SL {stop} | T1 {t1}"
        return AlertMessage(
            kind="ENTRY",
            symbol=symbol,
            title=f"ENTRY {symbol}",
            body_md=f"*{symbol}* — {body}",
            severity="INFO",
            deduplication_key=f"{symbol}:ENTRY:{on.isoformat()}",
        )

    def format_sl_breach(self, symbol: str, fill_price: Decimal, on: date) -> AlertMessage:
        return AlertMessage(
            kind="SL_BREACH",
            symbol=symbol,
            title=f"SL BREACH {symbol}",
            body_md=f"*{symbol}* stop hit, filled at {fill_price}",
            severity="URGENT",
            deduplication_key=f"{symbol}:SL_BREACH:{on.isoformat()}",
        )

    def format_sl_warning(self, symbol: str, price: Decimal, on: date) -> AlertMessage:
        return AlertMessage(
            kind="SL_WARNING",
            symbol=symbol,
            title=f"SL WARNING {symbol}",
            body_md=f"*{symbol}* approaching stop at {price}",
            severity="WARNING",
            deduplication_key=f"{symbol}:SL_WARNING:{on.isoformat()}",
        )

    def format_t1_hit(self, symbol: str, on: date) -> AlertMessage:
        return AlertMessage(
            kind="T1_HIT",
            symbol=symbol,
            title=f"T1 HIT {symbol}",
            body_md=f"*{symbol}* reached target 1 — consider trimming half position",
            severity="INFO",
            deduplication_key=f"{symbol}:T1_HIT:{on.isoformat()}",
        )

    def format_t2_hit(self, symbol: str, on: date) -> AlertMessage:
        return AlertMessage(
            kind="T2_HIT",
            symbol=symbol,
            title=f"T2 HIT {symbol}",
            body_md=f"*{symbol}* reached target 2 — consider exiting remainder",
            severity="INFO",
            deduplication_key=f"{symbol}:T2_HIT:{on.isoformat()}",
        )

    def format_regime_flip(self, prior_label: str, current_label: str, on: date) -> AlertMessage:
        return AlertMessage(
            kind="REGIME_FLIP",
            symbol=None,
            title="REGIME FLIP",
            body_md=f"Regime flipped *{prior_label}* -> *{current_label}*",
            severity="WARNING",
            deduplication_key=f"REGIME_FLIP:{on.isoformat()}",
        )

    def format_monday_revalidation(
        self, kept: list[str], killed: list[tuple[str, str]], on: date
    ) -> AlertMessage:
        kept_str = ", ".join(kept) or "none"
        killed_str = ", ".join(f"{s} ({reason})" for s, reason in killed) or "none"
        return AlertMessage(
            kind="MONDAY_REVALIDATION",
            symbol=None,
            title="MONDAY RE-VALIDATION",
            body_md=f"Kept: {kept_str}\nKilled: {killed_str}",
            severity="INFO",
            deduplication_key=f"MONDAY_REVALIDATION:{on.isoformat()}",
        )
