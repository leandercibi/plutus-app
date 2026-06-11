# src/plutus/alerts/channels.py
"""
Alert channel gateway.

TelegramChannel — sends via the existing bot (settings.TELEGRAM_BOT_TOKEN).
WhatsAppChannel — stub; raises NotImplementedError until Phase 8b wires the
                  WhatsApp Business Cloud API credentials.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class BaseChannel(ABC):
    name: str

    @abstractmethod
    def send(self, message: str) -> bool:
        """Attempt delivery. Returns True on success, False on failure."""


class TelegramChannel(BaseChannel):
    name = "telegram"

    def send(self, message: str) -> bool:
        try:
            from telegram import Bot
            from plutus.config import settings

            async def _send() -> None:
                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                await bot.send_message(
                    chat_id=settings.TELEGRAM_CHAT_ID,
                    text=message,
                    parse_mode="Markdown",
                )

            asyncio.run(_send())
            return True
        except Exception as exc:
            log.warning("TelegramChannel.send failed: %s", exc)
            return False


class WhatsAppChannel(BaseChannel):
    """Stub — interface defined so monitor.py doesn't need to change when impl lands."""

    name = "whatsapp"

    def send(self, message: str) -> bool:
        raise NotImplementedError(
            "WhatsApp Business Cloud API not yet configured. "
            "Set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN env vars, "
            "then implement this method in Phase 8b."
        )


def get_active_channels() -> list[BaseChannel]:
    """Return the channels that should receive alerts (based on env/config)."""
    channels: list[BaseChannel] = [TelegramChannel()]
    return channels
