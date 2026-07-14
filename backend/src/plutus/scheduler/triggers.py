from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger

_TZ = "Asia/Kolkata"


def sunday_full_run_trigger(hour: int = 19) -> CronTrigger:
    return CronTrigger(day_of_week="sun", hour=hour, minute=0, timezone=_TZ)


def monday_revalidation_trigger(hour: int = 9, minute: int = 10) -> CronTrigger:
    return CronTrigger(day_of_week="mon", hour=hour, minute=minute, timezone=_TZ)


def daily_exit_monitor_trigger(minutes: list[int]) -> CronTrigger:
    hours = sorted({m // 100 for m in minutes})
    mins = sorted({m % 100 for m in minutes})
    return CronTrigger(
        day_of_week="mon-fri",
        hour=",".join(str(h) for h in hours),
        minute=",".join(str(m) for m in mins),
        timezone=_TZ,
    )


def daily_freshness_trigger() -> CronTrigger:
    return CronTrigger(day_of_week="mon-fri", hour=9, minute=5, timezone=_TZ)


def weekly_postmortem_trigger() -> CronTrigger:
    return CronTrigger(day_of_week="sun", hour=21, minute=0, timezone=_TZ)


def midweek_mini_screen_trigger() -> CronTrigger:
    return CronTrigger(day_of_week="wed", hour=19, minute=0, timezone=_TZ)


def hourly_price_check_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week="mon-fri",
        hour="9-15",
        minute=30,
        timezone=_TZ,
    )


def daily_delivery_fetch_trigger(hour: int = 19, minute: int = 30) -> CronTrigger:
    return CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=_TZ)
