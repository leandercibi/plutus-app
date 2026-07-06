from __future__ import annotations

import logging

from plutus.alerts.channels import AlertChannel, AlertMessage, AlertResult
from plutus.alerts.monitor import AlertMonitor
from plutus.alerts.telegram import TelegramChannel
from plutus.alerts.whatsapp import build_whatsapp_channel
from plutus.config.settings import Settings
from plutus.swing.exits.cooldown import CooldownPolicy


class LogChannel:
    name = "log"

    def send(self, message: AlertMessage) -> AlertResult:
        logging.getLogger(__name__).info(
            "ALERT [%s] %s: %s", message.kind, message.symbol or "", message.title
        )
        return AlertResult(success=True, channel="log")


def build_alert_monitor(settings: Settings) -> AlertMonitor:
    channels: list[AlertChannel] = []
    if settings.telegram_bot_token is not None and settings.telegram_chat_id is not None:
        channels.append(
            TelegramChannel(
                token=settings.telegram_bot_token.get_secret_value(),
                chat_id=settings.telegram_chat_id,
            )
        )
    wa = build_whatsapp_channel(settings)
    if wa is not None:
        channels.append(wa)
    if not channels:
        channels.append(LogChannel())
    return AlertMonitor(channels, CooldownPolicy(settings))
