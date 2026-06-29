from __future__ import annotations

from plutus.config.settings import Settings
from plutus.scheduler.runner import build_scheduler


def test_build_scheduler_registers_core_jobs() -> None:
    sched = build_scheduler(Settings(_env_file=None))
    job_ids = {j.id for j in sched.get_jobs()}
    assert {
        "sunday_full_run",
        "monday_revalidation",
        "daily_exit_monitor",
        "daily_freshness_check",
        "weekly_postmortem_publish",
        "hourly_price_check",
    } <= job_ids


def test_midweek_job_gated_off_by_default() -> None:
    sched = build_scheduler(Settings(_env_file=None))
    assert "midweek_mini_screen" not in {j.id for j in sched.get_jobs()}


def test_midweek_job_registered_when_enabled() -> None:
    sched = build_scheduler(Settings(_env_file=None, midweek_mini_screen_enabled=True))
    assert "midweek_mini_screen" in {j.id for j in sched.get_jobs()}


def test_scheduler_uses_ist() -> None:
    sched = build_scheduler(Settings(_env_file=None))
    assert str(sched.timezone) == "Asia/Kolkata"
