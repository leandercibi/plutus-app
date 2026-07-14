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


def test_calls_far_apart_do_not_add_artificial_delay():
    _rate_wait()
    time.sleep(_MIN_INTERVAL + 0.05)  # already past the interval
    t0 = time.monotonic()
    _rate_wait()
    elapsed = time.monotonic() - t0
    # Should complete almost immediately — no extra sleep needed
    assert elapsed < _MIN_INTERVAL, (
        f"Unexpected extra delay: {elapsed:.3f}s (threshold {_MIN_INTERVAL}s)"
    )


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
    t.join(timeout=2.0)

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
    assert user_result == ["saturated"], "User-facing call should have given up quickly"
    assert background_result == [], "Background call should still be waiting"

    _mod._RATE_LOCK.release()
    bg.join(timeout=2.0)

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
