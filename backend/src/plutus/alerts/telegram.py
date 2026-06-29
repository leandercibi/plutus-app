from __future__ import annotations

import time

import requests

from plutus.alerts.channels import AlertMessage, AlertResult

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5


class TelegramChannel:
    name = "telegram"

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def send(self, message: AlertMessage) -> AlertResult:
        url = _API.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": f"*{message.title}*\n{message.body_md}",
            "parse_mode": "MarkdownV2",
        }
        last_error: str | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.post(url, json=payload, timeout=10)
            except requests.RequestException as exc:
                last_error = str(exc)
                _sleep_backoff(attempt)
                continue
            if resp.status_code == 200:
                msg_id = str(resp.json().get("result", {}).get("message_id"))
                return AlertResult(success=True, channel=self.name, message_id=msg_id)
            if 400 <= resp.status_code < 500:
                return AlertResult(
                    success=False,
                    channel=self.name,
                    error=f"client error {resp.status_code}",
                )
            last_error = f"server error {resp.status_code}"
            _sleep_backoff(attempt)
        return AlertResult(success=False, channel=self.name, error=last_error)


def _sleep_backoff(attempt: int) -> None:
    time.sleep(_BACKOFF_BASE_S * (2**attempt))
