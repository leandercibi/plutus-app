from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure tests never read a developer's real .env / environment secrets."""
    for key in list(os.environ):
        if key.startswith(
            (
                "RISK_",
                "ENVIRONMENT",
                "DB_URL",
                "LOG_LEVEL",
                "FRESHNESS_",
                "TELEGRAM_",
                "OPENROUTER_",
                "NEWSAPI_",
                "WHATSAPP_",
            )
        ):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    yield
