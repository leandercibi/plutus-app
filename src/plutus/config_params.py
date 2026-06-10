"""
config_params.py — DB-backed editable trading parameters (Phase 6).

Provides get_params() / set_param() / params_version_id() backed by the
`trading_params` table. Falls back to settings.* defaults if the DB row
doesn't exist yet (safe to call before migration).

Usage:
    from plutus.config_params import get_params, set_param

    p = get_params()
    p["initial_capital"]         # float: 100000.0
    p["max_risk_pct_per_trade"]  # float: 5.0
    p["buy_threshold"]           # int:   70
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ── Default values ─────────────────────────────────────────────────────────────
# These are the seeds used if the trading_params table is empty or missing.

PARAM_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "initial_capital":          {"value": 100_000.0, "type": "float", "min": 10_000,    "max": 10_000_000, "label": "Initial Capital (₹)"},
    "max_risk_pct_per_trade":   {"value": 5.0,       "type": "float", "min": 0.5,       "max": 5.0,        "label": "Max Risk % per Trade"},
    "min_rr_ratio":             {"value": 2.0,       "type": "float", "min": 1.5,       "max": 4.0,        "label": "Min R:R Ratio"},
    "hold_days_min":            {"value": 3,         "type": "int",   "min": 1,         "max": 30,         "label": "Hold Days (Min)"},
    "hold_days_max":            {"value": 10,        "type": "int",   "min": 1,         "max": 30,         "label": "Hold Days (Max)"},
    "max_open_positions":       {"value": 4,         "type": "int",   "min": 1,         "max": 20,         "label": "Max Open Positions"},
    "max_pct_capital_per_trade":{"value": 30.0,      "type": "float", "min": 5.0,       "max": 50.0,       "label": "Max % Capital per Trade"},
    "buy_threshold":            {"value": 70,        "type": "int",   "min": 60,        "max": 90,         "label": "BUY Score Threshold"},
    "watch_threshold":          {"value": 55,        "type": "int",   "min": 40,        "max": 70,         "label": "WATCH Score Threshold"},
    "avoid_threshold":          {"value": 35,        "type": "int",   "min": 20,        "max": 50,         "label": "AVOID Score Threshold"},
}


def _cast(value_str: str, value_type: str) -> Any:
    if value_type == "int":
        return int(float(value_str))
    if value_type == "float":
        return float(value_str)
    return value_str


def _ensure_seeded(db_session) -> None:
    """Insert default rows for any param_key not yet in the DB."""
    from plutus.db.models import TradingParam
    for key, meta in PARAM_DEFAULTS.items():
        existing = db_session.query(TradingParam).filter_by(param_key=key).first()
        if not existing:
            db_session.add(TradingParam(
                param_key=key,
                value=str(meta["value"]),
                value_type=meta["type"],
                min_allowed=meta.get("min"),
                max_allowed=meta.get("max"),
                label=meta.get("label"),
                updated_by="system",
            ))
    db_session.commit()


def get_params(db_session=None) -> Dict[str, Any]:
    """
    Return all trading params as a dict.
    Values are cast to their native types (int / float / str).
    Falls back to PARAM_DEFAULTS on any DB failure.
    """
    try:
        from plutus.db.models import TradingParam
        from plutus.db.session import SessionLocal

        ctx = db_session or SessionLocal()
        close_ctx = db_session is None
        try:
            _ensure_seeded(ctx)
            rows = ctx.query(TradingParam).all()
            result = {}
            for row in rows:
                result[row.param_key] = _cast(row.value, row.value_type)
            # Fill any missing keys from defaults (e.g. new keys added after seeding)
            for key, meta in PARAM_DEFAULTS.items():
                if key not in result:
                    result[key] = meta["value"]
            return result
        finally:
            if close_ctx:
                ctx.close()
    except Exception as exc:
        log.warning("get_params DB fallback: %s", exc)
        return {k: v["value"] for k, v in PARAM_DEFAULTS.items()}


def get_param_meta(db_session=None) -> Dict[str, Dict[str, Any]]:
    """Return full metadata (value, type, min, max, label) for all params."""
    try:
        from plutus.db.models import TradingParam
        from plutus.db.session import SessionLocal

        ctx = db_session or SessionLocal()
        close_ctx = db_session is None
        try:
            _ensure_seeded(ctx)
            rows = ctx.query(TradingParam).all()
            return {
                row.param_key: {
                    "value": _cast(row.value, row.value_type),
                    "value_type": row.value_type,
                    "min": row.min_allowed,
                    "max": row.max_allowed,
                    "label": row.label or row.param_key,
                    "updated_at": row.updated_at,
                }
                for row in rows
            }
        finally:
            if close_ctx:
                ctx.close()
    except Exception:
        return {
            k: {"value": v["value"], "value_type": v["type"],
                "min": v.get("min"), "max": v.get("max"), "label": v.get("label")}
            for k, v in PARAM_DEFAULTS.items()
        }


def set_param(key: str, value: Any, updated_by: str = "dashboard", db_session=None) -> None:
    """
    Update a single trading param. Validates against min/max bounds.
    Raises ValueError on invalid input.
    """
    if key not in PARAM_DEFAULTS:
        raise ValueError(f"Unknown param key: {key!r}")

    meta = PARAM_DEFAULTS[key]
    cast_value = _cast(str(value), meta["type"])

    if meta.get("min") is not None and cast_value < meta["min"]:
        raise ValueError(f"{key}: {cast_value} < minimum {meta['min']}")
    if meta.get("max") is not None and cast_value > meta["max"]:
        raise ValueError(f"{key}: {cast_value} > maximum {meta['max']}")

    from plutus.db.models import TradingParam
    from plutus.db.session import SessionLocal
    from datetime import datetime

    ctx = db_session or SessionLocal()
    close_ctx = db_session is None
    try:
        row = ctx.query(TradingParam).filter_by(param_key=key).first()
        if row:
            row.value = str(cast_value)
            row.updated_by = updated_by
            row.updated_at = datetime.utcnow()
        else:
            ctx.add(TradingParam(
                param_key=key,
                value=str(cast_value),
                value_type=meta["type"],
                min_allowed=meta.get("min"),
                max_allowed=meta.get("max"),
                label=meta.get("label"),
                updated_by=updated_by,
            ))
        ctx.commit()
        log.info("set_param: %s = %s (by %s)", key, cast_value, updated_by)
    finally:
        if close_ctx:
            ctx.close()


def params_version_id(params: Optional[Dict[str, Any]] = None) -> str:
    """
    Return a short hash of the current trading params.
    Used to stamp weekly_runs rows so backtests are reproducible.
    """
    if params is None:
        params = get_params()
    serialised = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()[:16]
