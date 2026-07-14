"""End-to-end tests for AngelOne rate-limiter concurrency behaviour.

Covers:
  - Minimum interval between calls is enforced
  - Background callers (timeout=None) block until the lock is free
  - User-facing callers (timeout=float) raise RateLimitSaturated when saturated
  - Lock is always released after RateLimitSaturated (no deadlock)
  - AngelOneProvider(rate_limit_timeout=None) passes None to _rate_wait (background)
  - AngelOneProvider(rate_limit_timeout=5.0) passes 5.0 to _rate_wait (user-facing)
  - Concurrent background + user-facing: user raises, background eventually succeeds
"""

from __future__ import annotations

import contextlib
import threading
import time

import pytest

import plutus.data.providers.angelone_provider as _mod
from plutus.data.providers.angelone_provider import (
    _MIN_INTERVAL,
    USER_RATE_LIMIT_TIMEOUT,
    RateLimitSaturated,
    _rate_wait,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_rate_state() -> None:
    """Reset module-level rate-limiter state between tests."""
    # Release the lock if somehow held (shouldn't happen, but defensive)
    with contextlib.suppress(RuntimeError):
        _mod._RATE_LOCK.release()
    _mod._LAST_CALL[0] = 0.0


@pytest.fixture(autouse=True)
def reset_rate(monkeypatch):
    """Each test starts with a clean rate-limiter slate."""
    _reset_rate_state()
    yield
    _reset_rate_state()


# ---------------------------------------------------------------------------
# Interval enforcement
# ---------------------------------------------------------------------------


def test_two_consecutive_calls_respect_min_interval():
    t0 = time.monotonic()
    _rate_wait()
    _rate_wait()
    elapsed = time.monotonic() - t0
    assert elapsed >= _MIN_INTERVAL, (
        f"Two calls took only {elapsed:.3f}s; expected >= {_MIN_INTERVAL}s between them"
    )


def test_calls_far_apart_do_not_add_artificial_delay(monkeypatch):
    """When enough real time has already passed, _rate_wait must not add an
    artificial extra sleep. Simulates the elapsed time by rewinding _LAST_CALL
    instead of a real time.sleep(): a real wall-clock measurement here was
    intermittently flaky under system load (OS scheduling jitter routinely
    blew past the tight assertion threshold when the full suite was running)."""
    sleep_calls: list[float] = []
    monkeypatch.setattr(_mod.time, "sleep", lambda s: sleep_calls.append(s))

    _rate_wait()  # first call — sets _LAST_CALL
    _mod._LAST_CALL[0] -= _MIN_INTERVAL + 0.05  # simulate time already elapsed

    _rate_wait()  # second call — should see it's already past the interval

    assert sleep_calls == [], f"Unexpected artificial delay: slept for {sleep_calls}"


# ---------------------------------------------------------------------------
# Timeout=None: blocks indefinitely
# ---------------------------------------------------------------------------


def test_background_caller_blocks_until_lock_released():
    """A timeout=None caller must wait for a held lock and then succeed."""
    _mod._RATE_LOCK.acquire()  # simulate lock held by another thread

    results: list[str] = []

    def background_call():
        try:
            _rate_wait(timeout=None)  # should block
            results.append("ok")
        except RateLimitSaturated:
            results.append("saturated")

    t = threading.Thread(target=background_call)
    t.start()

    time.sleep(0.05)  # give the thread a moment to reach the lock
    assert results == [], "Should still be blocked"

    _mod._RATE_LOCK.release()  # unblock it
    t.join(timeout=10.0)
    # A thread still alive here would keep running after this test returns and could
    # release/acquire the shared module-level lock mid-way through a later test —
    # fail loudly now instead of leaking a zombie thread that corrupts other tests.
    assert not t.is_alive(), "Background thread did not finish within the join timeout"

    assert results == ["ok"], "Background caller should have succeeded after lock released"


# ---------------------------------------------------------------------------
# Timeout=float: fails fast
# ---------------------------------------------------------------------------


def test_user_caller_raises_when_lock_held():
    """A user-facing caller with a short timeout must raise RateLimitSaturated."""
    _mod._RATE_LOCK.acquire()  # hold the lock
    try:
        with pytest.raises(RateLimitSaturated, match="rate limiter saturated"):
            _rate_wait(timeout=0.05)
    finally:
        _mod._RATE_LOCK.release()


def test_lock_released_after_rate_limit_saturated():
    """After RateLimitSaturated the lock must not be held — next call succeeds."""
    _mod._RATE_LOCK.acquire()

    with contextlib.suppress(RateLimitSaturated):
        _rate_wait(timeout=0.05)

    _mod._RATE_LOCK.release()  # release what we acquired above

    # Next call should succeed without hanging
    _rate_wait(timeout=0.5)  # would raise/block if lock were stuck


def test_user_timeout_value_is_respected():
    """The caller should give up close to the requested timeout, not sooner or much later."""
    _mod._RATE_LOCK.acquire()
    timeout = 0.15
    t0 = time.monotonic()
    try:
        _rate_wait(timeout=timeout)
    except RateLimitSaturated:
        pass
    finally:
        _mod._RATE_LOCK.release()
    elapsed = time.monotonic() - t0
    assert timeout * 0.5 <= elapsed <= timeout + 0.1, (
        f"Expected to wait ~{timeout}s, actually waited {elapsed:.3f}s"
    )


# ---------------------------------------------------------------------------
# Concurrent scenario: cron sweeping + user refresh
# ---------------------------------------------------------------------------


def test_concurrent_background_and_user_calls():
    """Simulates a cron sweep holding the lock while a user refresh arrives.

    Background call (timeout=None) → eventually succeeds.
    User call (timeout=0.05) → raises RateLimitSaturated immediately.
    """
    # Hold the lock to simulate the pipeline mid-call
    _mod._RATE_LOCK.acquire()

    background_result: list[str] = []
    user_result: list[str] = []

    def background():
        try:
            _rate_wait(timeout=None)
            background_result.append("ok")
        except RateLimitSaturated:
            background_result.append("saturated")

    def user_refresh():
        try:
            _rate_wait(timeout=0.05)
            user_result.append("ok")
        except RateLimitSaturated:
            user_result.append("saturated")

    bg = threading.Thread(target=background)
    usr = threading.Thread(target=user_refresh)

    bg.start()
    usr.start()

    time.sleep(0.1)  # user call should have timed out by now
    usr.join(timeout=10.0)
    assert not usr.is_alive(), "User-facing thread did not finish within the join timeout"
    assert user_result == ["saturated"], "User-facing call should have given up quickly"
    assert background_result == [], "Background call should still be waiting"

    _mod._RATE_LOCK.release()
    bg.join(timeout=10.0)
    # Same reasoning as test_background_caller_blocks_until_lock_released: don't let
    # a slow-under-load thread outlive this test and corrupt a later one's lock state.
    assert not bg.is_alive(), "Background thread did not finish within the join timeout"

    assert background_result == ["ok"], "Background call should succeed once lock freed"


# ---------------------------------------------------------------------------
# AngelOneProvider construction wires the timeout correctly
# ---------------------------------------------------------------------------


def test_provider_default_timeout_is_none(monkeypatch):
    """AngelOneProvider() with no rate_limit_timeout passes None to _rate_wait."""
    calls: list[float | None] = []

    def capture_timeout(timeout=None):
        calls.append(timeout)

    monkeypatch.setattr(_mod, "_rate_wait", capture_timeout)
    monkeypatch.setattr(_mod, "_resolve_token", lambda s: "TOKEN")

    class _FakeSession:
        def ltpData(self, *a, **kw):
            return {"status": True, "data": {"ltp": 100.0}}

    monkeypatch.setattr(_mod, "_get_session", lambda *a, **kw: _FakeSession())

    provider = _mod.AngelOneProvider("k", "c", "p", "t")  # no rate_limit_timeout
    provider.fetch_ltp("RELIANCE")

    assert calls[0] is None, f"Expected timeout=None for background provider, got {calls[0]}"


def test_provider_user_timeout_is_forwarded(monkeypatch):
    """AngelOneProvider(rate_limit_timeout=5.0) passes 5.0 to _rate_wait."""
    calls: list[float | None] = []

    def capture_timeout(timeout=None):
        calls.append(timeout)

    monkeypatch.setattr(_mod, "_rate_wait", capture_timeout)
    monkeypatch.setattr(_mod, "_resolve_token", lambda s: "TOKEN")

    class _FakeSession:
        def ltpData(self, *a, **kw):
            return {"status": True, "data": {"ltp": 200.0}}

    monkeypatch.setattr(_mod, "_get_session", lambda *a, **kw: _FakeSession())

    provider = _mod.AngelOneProvider("k", "c", "p", "t", rate_limit_timeout=5.0)
    provider.fetch_ltp("INFY")

    assert calls[0] == 5.0, f"Expected timeout=5.0 for user-facing provider, got {calls[0]}"


def test_user_rate_limit_timeout_constant():
    assert USER_RATE_LIMIT_TIMEOUT == 5.0
