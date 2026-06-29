from __future__ import annotations

import responses

from plutus.alerts.channels import AlertMessage
from plutus.alerts.telegram import TelegramChannel

_URL = "https://api.telegram.org/bottoken/sendMessage"


def _msg() -> AlertMessage:
    return AlertMessage(
        kind="ENTRY",
        symbol="INFY",
        title="ENTRY INFY",
        body_md="*INFY* entry",
        severity="INFO",
        deduplication_key="INFY:ENTRY:2025-01-01",
    )


@responses.activate
def test_successful_post_returns_success() -> None:
    responses.add(responses.POST, _URL, json={"result": {"message_id": 42}}, status=200)
    ch = TelegramChannel(token="token", chat_id="chat")
    result = ch.send(_msg())
    assert result.success
    assert result.message_id == "42"


@responses.activate
def test_500_retries_three_times(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import plutus.alerts.telegram as tg

    monkeypatch.setattr(tg, "_sleep_backoff", lambda attempt: None)
    responses.add(responses.POST, _URL, status=500)
    responses.add(responses.POST, _URL, status=500)
    responses.add(responses.POST, _URL, status=500)
    ch = TelegramChannel(token="token", chat_id="chat")
    result = ch.send(_msg())
    assert result.success is False
    assert len(responses.calls) == 3


@responses.activate
def test_401_fails_fast(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import plutus.alerts.telegram as tg

    monkeypatch.setattr(tg, "_sleep_backoff", lambda attempt: None)
    responses.add(responses.POST, _URL, status=401)
    ch = TelegramChannel(token="token", chat_id="chat")
    result = ch.send(_msg())
    assert result.success is False
    assert len(responses.calls) == 1  # no retry on 4xx
