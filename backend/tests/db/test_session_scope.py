from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plutus.db import session as session_mod
from plutus.db.models import Base, Universe
from plutus.db.session import get_engine, session_scope


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    session_mod.reset_engine_for_tests("sqlite:///:memory:")
    Base.metadata.create_all(get_engine())


def _row() -> Universe:
    return Universe(
        symbol="INFY",
        as_of_date=date(2025, 1, 1),
        median_traded_value_inr=Decimal("100000000"),
        in_universe=True,
    )


def test_clean_commit_persists() -> None:
    with session_scope() as s:
        s.add(_row())
    with session_scope() as s:
        assert s.query(Universe).count() == 1


def test_exception_inside_block_rolls_back() -> None:
    class Boom(Exception):
        pass

    with pytest.raises(Boom), session_scope() as s:
        s.add(_row())
        s.flush()
        raise Boom()

    with session_scope() as s:
        assert s.query(Universe).count() == 0
