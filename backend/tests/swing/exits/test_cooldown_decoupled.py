from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from plutus.config.settings import Settings
from plutus.swing.exits.cooldown import CooldownPolicy


@pytest.fixture
def policy() -> CooldownPolicy:
    return CooldownPolicy(Settings(_env_file=None))


@pytest.mark.hallmark
def test_sl_breach_always_fires_even_right_after_warning(
    policy: CooldownPolicy, session: Session
) -> None:
    """A16 hallmark: SL_BREACH is never suppressed by any cooldown."""
    now = datetime(2025, 1, 6, 10, 0, 0)
    # fire SL_WARNING and record its cooldown
    assert policy.can_fire("INFY", "SL_WARNING", now, session) is True
    policy.record_fired("INFY", "SL_WARNING", now, session)
    session.commit()

    # within the hour, SL_BREACH must still fire immediately
    later = now + timedelta(minutes=5)
    assert policy.can_fire("INFY", "SL_BREACH", later, session) is True


def test_sl_breach_repeated_always_fires(
    policy: CooldownPolicy, session: Session
) -> None:
    now = datetime(2025, 1, 6, 10, 0, 0)
    assert policy.can_fire("INFY", "SL_BREACH", now, session) is True
    policy.record_fired("INFY", "SL_BREACH", now, session)
    session.commit()
    assert (
        policy.can_fire("INFY", "SL_BREACH", now + timedelta(minutes=1), session)
        is True
    )


def test_other_kind_respects_cooldown(policy: CooldownPolicy, session: Session) -> None:
    now = datetime(2025, 1, 6, 10, 0, 0)
    assert policy.can_fire("INFY", "T1_HIT", now, session) is True
    policy.record_fired("INFY", "T1_HIT", now, session)
    session.commit()
    # within cooldown window -> suppressed
    assert (
        policy.can_fire("INFY", "T1_HIT", now + timedelta(minutes=30), session) is False
    )
    # after cooldown window -> allowed again
    assert (
        policy.can_fire("INFY", "T1_HIT", now + timedelta(minutes=61), session) is True
    )


def test_kinds_are_independent_per_symbol(
    policy: CooldownPolicy, session: Session
) -> None:
    now = datetime(2025, 1, 6, 10, 0, 0)
    policy.record_fired("INFY", "SL_WARNING", now, session)
    session.commit()
    # NO_PROGRESS for same symbol is a separate key, unaffected
    assert (
        policy.can_fire("INFY", "NO_PROGRESS", now + timedelta(minutes=1), session)
        is True
    )
    # SL_WARNING for a different symbol is unaffected
    assert (
        policy.can_fire("TCS", "SL_WARNING", now + timedelta(minutes=1), session)
        is True
    )
    # SL_WARNING same symbol within cooldown -> suppressed
    assert (
        policy.can_fire("INFY", "SL_WARNING", now + timedelta(minutes=1), session)
        is False
    )
