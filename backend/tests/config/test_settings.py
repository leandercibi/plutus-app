from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from plutus.config.settings import Settings, get_settings


def test_defaults_load() -> None:
    s = Settings(_env_file=None)
    assert s.risk_per_trade_pct == 0.01
    assert s.environment == "test"
    assert s.expectancy_floor_R == 0.3


def test_env_file_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("RISK_PER_TRADE_PCT=0.005\n")
    s = Settings(_env_file=str(env))
    assert s.risk_per_trade_pct == 0.005


def test_prod_rejects_sqlite() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="prod", db_url="sqlite:///./plutus.db")


def test_prod_rejects_freshness_off() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="prod",
            db_url="postgresql+psycopg://u@h/db",
            freshness_assert_enabled=False,
        )


def test_risk_above_2pct_rejected_in_prod() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="prod",
            db_url="postgresql+psycopg://u@h/db",
            risk_per_trade_pct=0.03,
        )


def test_secret_not_logged() -> None:
    s = Settings(_env_file=None, telegram_bot_token="super-secret-token-123")
    assert "super-secret-token-123" not in repr(s)


def test_pct_field_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sector_cap_pct_of_pool=1.5)


def test_expectancy_floor_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, expectancy_floor_R=0.0)


def test_get_settings_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
