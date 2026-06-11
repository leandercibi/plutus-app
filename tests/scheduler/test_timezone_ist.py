from __future__ import annotations

from plutus.scheduler.triggers import (
    daily_exit_monitor_trigger,
    monday_revalidation_trigger,
    sunday_full_run_trigger,
)


def test_triggers_use_ist_timezone() -> None:
    for trigger in (
        sunday_full_run_trigger(),
        monday_revalidation_trigger(),
        daily_exit_monitor_trigger([930, 1015, 1500]),
    ):
        assert str(trigger.timezone) == "Asia/Kolkata"


def test_monday_trigger_is_0910() -> None:
    t = monday_revalidation_trigger(9, 10)
    fields = {f.name: str(f) for f in t.fields}
    assert fields["hour"] == "9"
    assert fields["minute"] == "10"
    assert fields["day_of_week"] == "mon"
