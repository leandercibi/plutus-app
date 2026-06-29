from __future__ import annotations

import logging

from plutus.config.logging import get_logger


def test_get_logger_returns_named_logger() -> None:
    log = get_logger("plutus.test")
    assert isinstance(log, logging.Logger)
    assert log.name == "plutus.test"


def test_get_logger_idempotent() -> None:
    a = get_logger("plutus.same")
    b = get_logger("plutus.same")
    assert a is b
