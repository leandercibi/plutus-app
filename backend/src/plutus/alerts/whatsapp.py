from __future__ import annotations

from plutus.alerts.channels import AlertChannel
from plutus.config.settings import Settings


def build_whatsapp_channel(settings: Settings) -> AlertChannel | None:
    """Optional. Returns None unless settings.whatsapp_api_key is set."""
    if settings.whatsapp_api_key is None:
        return None
    return _WhatsAppChannel(settings.whatsapp_api_key.get_secret_value())


class _WhatsAppChannel:
    name = "whatsapp"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def send(self, message: object) -> object:  # pragma: no cover - optional path
        raise NotImplementedError("WhatsApp delivery is configured but not wired in P1")
