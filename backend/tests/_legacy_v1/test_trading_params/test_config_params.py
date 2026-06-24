# tests/test_trading_params/test_config_params.py
"""
Tests for config_params.py — in-memory SQLite, no network.

Verifies:
  - get_params() returns all default keys with correct types
  - set_param() persists and is immediately readable
  - set_param() validates min/max bounds
  - set_param() rejects unknown keys
  - params_version_id() changes when a param changes
  - get_params() falls back to defaults on empty DB
  - build_risk_manager_prompt() uses live param values
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from plutus.db.session import Base
from plutus.config_params import (
    PARAM_DEFAULTS,
    get_params,
    get_param_meta,
    set_param,
    params_version_id,
)
from plutus.agents.prompts import build_risk_manager_prompt


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestGetParams:
    def test_returns_all_default_keys(self, db):
        params = get_params(db_session=db)
        for key in PARAM_DEFAULTS:
            assert key in params, f"Missing key: {key}"

    def test_default_values_match_spec(self, db):
        params = get_params(db_session=db)
        assert params["initial_capital"] == pytest.approx(100_000.0)
        assert params["max_risk_pct_per_trade"] == pytest.approx(5.0)
        assert params["min_rr_ratio"] == pytest.approx(2.0)
        assert params["buy_threshold"] == 70
        assert params["watch_threshold"] == 55
        assert params["avoid_threshold"] == 35

    def test_int_params_are_ints(self, db):
        params = get_params(db_session=db)
        assert isinstance(params["hold_days_min"], int)
        assert isinstance(params["hold_days_max"], int)
        assert isinstance(params["max_open_positions"], int)
        assert isinstance(params["buy_threshold"], int)

    def test_float_params_are_floats(self, db):
        params = get_params(db_session=db)
        assert isinstance(params["initial_capital"], float)
        assert isinstance(params["max_risk_pct_per_trade"], float)
        assert isinstance(params["min_rr_ratio"], float)


class TestSetParam:
    def test_set_and_retrieve(self, db):
        set_param("initial_capital", 200_000.0, db_session=db)
        params = get_params(db_session=db)
        assert params["initial_capital"] == pytest.approx(200_000.0)

    def test_set_int_param(self, db):
        set_param("buy_threshold", 75, db_session=db)
        params = get_params(db_session=db)
        assert params["buy_threshold"] == 75
        assert isinstance(params["buy_threshold"], int)

    def test_rejects_below_min(self, db):
        with pytest.raises(ValueError, match="minimum"):
            set_param("max_risk_pct_per_trade", 0.1, db_session=db)

    def test_rejects_above_max(self, db):
        with pytest.raises(ValueError, match="maximum"):
            set_param("max_risk_pct_per_trade", 10.0, db_session=db)

    def test_rejects_unknown_key(self, db):
        with pytest.raises(ValueError, match="Unknown param key"):
            set_param("nonexistent_param", 42, db_session=db)

    def test_update_existing_row(self, db):
        set_param("min_rr_ratio", 2.5, db_session=db)
        set_param("min_rr_ratio", 3.0, db_session=db)
        params = get_params(db_session=db)
        assert params["min_rr_ratio"] == pytest.approx(3.0)

    def test_at_min_boundary_accepted(self, db):
        set_param("max_risk_pct_per_trade", 0.5, db_session=db)
        assert get_params(db_session=db)["max_risk_pct_per_trade"] == pytest.approx(0.5)

    def test_at_max_boundary_accepted(self, db):
        set_param("max_risk_pct_per_trade", 5.0, db_session=db)
        assert get_params(db_session=db)["max_risk_pct_per_trade"] == pytest.approx(5.0)


class TestParamsVersionId:
    def test_same_params_same_version(self, db):
        v1 = params_version_id(get_params(db_session=db))
        v2 = params_version_id(get_params(db_session=db))
        assert v1 == v2

    def test_different_params_different_version(self, db):
        p1 = get_params(db_session=db)
        v1 = params_version_id(p1)
        set_param("initial_capital", 150_000.0, db_session=db)
        p2 = get_params(db_session=db)
        v2 = params_version_id(p2)
        assert v1 != v2

    def test_version_is_16_chars(self, db):
        v = params_version_id(get_params(db_session=db))
        assert len(v) == 16
        assert all(c in "0123456789abcdef" for c in v)


class TestGetParamMeta:
    def test_returns_min_max_label(self, db):
        meta = get_param_meta(db_session=db)
        for key in PARAM_DEFAULTS:
            assert key in meta
            assert "min" in meta[key]
            assert "max" in meta[key]
            assert "label" in meta[key]

    def test_label_is_non_empty(self, db):
        meta = get_param_meta(db_session=db)
        for key, m in meta.items():
            assert m["label"], f"{key}: empty label"


class TestBuildRiskManagerPrompt:
    def test_renders_custom_capital(self):
        prompt = build_risk_manager_prompt(
            {
                "initial_capital": 50_000.0,
                "max_risk_pct_per_trade": 3.0,
                "min_rr_ratio": 2.0,
                "max_open_positions": 3,
                "max_pct_capital_per_trade": 25.0,
            }
        )
        assert "50,000" in prompt
        assert "3.0%" in prompt or "3%" in prompt

    def test_renders_default_values_without_params(self):
        prompt = build_risk_manager_prompt(None)
        assert "₹" in prompt
        assert len(prompt) > 100

    def test_contains_rr_ratio(self):
        prompt = build_risk_manager_prompt(
            {
                "initial_capital": 100_000.0,
                "max_risk_pct_per_trade": 5.0,
                "min_rr_ratio": 2.5,
                "max_open_positions": 4,
                "max_pct_capital_per_trade": 30.0,
            }
        )
        assert "2.5" in prompt
