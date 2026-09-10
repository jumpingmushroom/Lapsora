"""Standard-cron -> APScheduler day-of-week translation.

APScheduler's week starts on Monday, rejects 7 as an alias for Sunday, and
refuses ranges that wrap past Sunday. The stored expressions (and the UI's
presets, which label '* * * * 0' as Sunday) use ordinary cron semantics, so
every case here pins the *actual firing day* rather than the translated text.
"""

from datetime import datetime, timedelta, timezone

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.cron_utils import cron_trigger_kwargs, normalize_cron_day_of_week

# A Sunday, so the first fire time never straddles the week boundary.
_ANCHOR = datetime(2026, 9, 6, tzinfo=timezone.utc)


def _firing_days(expr: str) -> set[str]:
    """The weekdays a cron expression actually fires on, per APScheduler."""
    trigger = CronTrigger(**cron_trigger_kwargs(expr))
    days, cursor = set(), _ANCHOR
    for _ in range(10):
        nxt = trigger.get_next_fire_time(None, cursor)
        if nxt is None:
            break
        days.add(nxt.strftime("%a"))
        cursor = nxt + timedelta(minutes=1)
    return days


@pytest.mark.parametrize(
    "dow,expected",
    [
        ("0", {"Sun"}),                                  # cron 0 is Sunday, not Monday
        ("1", {"Mon"}),
        ("6", {"Sat"}),
        ("7", {"Sun"}),                                  # 7 is a second alias for Sunday
        ("0-2", {"Sun", "Mon", "Tue"}),
        ("1-5", {"Mon", "Tue", "Wed", "Thu", "Fri"}),
        ("5-1", {"Fri", "Sat", "Sun", "Mon"}),           # wraps past the week's end
        ("*/2", {"Sun", "Tue", "Thu", "Sat"}),           # steps count from Sunday
        ("0-6/3", {"Sun", "Wed", "Sat"}),
        ("0,3", {"Sun", "Wed"}),
        ("sun", {"Sun"}),                                # names pass through untouched
        ("mon-fri", {"Mon", "Tue", "Wed", "Thu", "Fri"}),
        ("*", {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}),
    ],
)
def test_day_of_week_fires_on_standard_cron_days(dow, expected):
    assert _firing_days(f"0 0 * * {dow}") == expected


def test_weekly_presets_fire_on_sunday():
    """Both presets are labelled Sunday in the UI; they must fire on Sunday."""
    from app.routers.timelapse_schedules import PRESET_CRONS

    assert _firing_days(PRESET_CRONS["weekly"]) == {"Sun"}
    assert _firing_days("0 3 * * 0") == {"Sun"}  # CleanupScheduleManager 'Weekly Sun 03:00'


def test_non_weekly_presets_are_unaffected():
    from app.routers.timelapse_schedules import PRESET_CRONS

    for preset in ("daily", "monthly", "yearly"):
        kwargs = cron_trigger_kwargs(PRESET_CRONS[preset])
        assert kwargs["day_of_week"] == "*"


@pytest.mark.parametrize(
    "expr", ["0 0 * * 9", "0 0 * * 0-9", "0 0 * * 1/0", "0 0 * * ", "not a cron", "0 0 * *"]
)
def test_malformed_expressions_raise(expr):
    with pytest.raises(ValueError):
        CronTrigger(**cron_trigger_kwargs(expr))


@pytest.mark.parametrize("expr", ["0 0 * * abc", "0 0 * * mon-xyz"])
def test_unknown_day_names_still_reach_apscheduler(expr):
    """Names are passed through, so APScheduler stays the one validator."""
    assert normalize_cron_day_of_week(expr.split()[-1]) == expr.split()[-1]
    with pytest.raises(ValueError):
        CronTrigger(**cron_trigger_kwargs(expr))


def test_duplicate_days_collapse():
    assert normalize_cron_day_of_week("0,0,7") == "sun"
