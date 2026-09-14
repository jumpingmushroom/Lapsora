"""Does a render period boundary fall inside a capture window?

A render schedule gathers frames over a clock window. When that window's edge
lands in the middle of a capture session, the render holds the end of one
session and the start of the next — the "split night" bug: a sunset-to-sunrise
plan rendered daily at 00:05 produces dawn, then an abrupt cut to dusk, from
two different nights.

The test is not "does this plan span midnight?". That rule would need its own
handling for sun events, manual wraps and sun_offset_minutes, and would drift
from the thing it describes. The test is simply: *would this plan be capturing
at the moment the boundary falls?* — asked of `_is_within_active_window`, the
function the capture job itself gates on.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Sun windows move through the year, so one sample is not enough: a boundary
# that is safe in September can split in December. These four dates bracket the
# extremes at any latitude. A schedule that is correct for half the year is
# still a bug, just a seasonal one.
_SAMPLE_DAYS = ((1, 15), (4, 15), (7, 15), (10, 15))

# The pivot to move a splitting boundary to. Midday is the point furthest from
# any night, and holds year-round at Nordic latitudes: midsummer (sunset 22:45,
# sunrise 04:00) and midwinter (sunset 15:15, sunrise 09:15) both sit entirely
# inside a midday-to-midday window.
SAFE_HOUR = 12
SAFE_MINUTE = 0


def parse_cron_time(expression: str) -> tuple[int, int] | None:
    """The (hour, minute) a 5-field cron fires at, when it is a fixed time.

    Returns None for expressions with steps or lists in the hour or minute
    fields — those fire repeatedly, so there is no single boundary to reason
    about and no safe rewrite to offer.
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        return None
    minute, hour = parts[0], parts[1]
    if not minute.isdigit() or not hour.isdigit():
        return None
    m, h = int(minute), int(hour)
    if not (0 <= m < 60 and 0 <= h < 24):
        return None
    return h, m


def _sample_instants(hour: int, minute: int, year: int) -> list[datetime]:
    return [
        datetime(year, month, day, hour, minute).astimezone()
        for month, day in _SAMPLE_DAYS
    ]


def boundary_splits_window(profile, db, hour: int, minute: int, year: int | None = None) -> bool:
    """True when a boundary at this local time falls inside the plan's window.

    Sampled across the year; splitting on any sample counts. An `always` plan
    captures continuously and has no session to split, so it never does.
    """
    if profile.capture_mode == "always":
        return False

    from app.services.capture import _is_within_active_window

    year = year or datetime.now().year
    for when in _sample_instants(hour, minute, year):
        try:
            if _is_within_active_window(profile, db, when):
                return True
        except Exception:
            # Matches capture.py, which allows capture when the window cannot
            # be computed. Treating that as "splitting" would rewrite crons on
            # the strength of a failure.
            logger.warning(
                "Could not evaluate the active window for profile %s at %s",
                getattr(profile, "id", "?"), when,
            )
    return False


def safe_boundary(profile, db, hour: int, minute: int) -> tuple[int, int] | None:
    """A boundary that does not split this plan's window, or None.

    Returns the given boundary unchanged when it is already clean, midday when
    that fixes it, and None when no boundary is clean — a plan capturing
    `daylight, night` is active around the clock, and pretending midday helps
    would be worse than the bug.
    """
    if not boundary_splits_window(profile, db, hour, minute):
        return hour, minute
    if not boundary_splits_window(profile, db, SAFE_HOUR, SAFE_MINUTE):
        return SAFE_HOUR, SAFE_MINUTE
    return None


def realign_cron(profile, db, expression: str) -> str:
    """Shift a cron's fire time so it does not cut the plan's window in half.

    Day/month/weekday fields are left alone: only the hour and minute decide
    where the boundary lands. Anything unparseable is returned untouched.
    """
    parsed = parse_cron_time(expression)
    if parsed is None:
        return expression
    hour, minute = parsed
    safe = safe_boundary(profile, db, hour, minute)
    if safe is None or safe == (hour, minute):
        return expression
    parts = expression.strip().split()
    parts[0], parts[1] = str(safe[1]), str(safe[0])
    return " ".join(parts)


def captures_continuously(profile, db) -> bool:
    """True when no boundary is clean, so the user should be told rather than
    silently given a cron that is no better than the one they picked."""
    if profile.capture_mode == "always":
        return False
    for hour in range(0, 24, 3):
        if not boundary_splits_window(profile, db, hour, 0):
            return False
    return True


def describe_period(profile, db, preset: str) -> str:
    """What a preset covers for this plan, for labelling.

    A preset shifted to midday is no longer "daily at 00:05" in any meaningful
    sense — for an overnight plan the period *is* the night, and the label
    should follow the content rather than the clock.
    """
    if preset == "daily" and boundary_splits_window(profile, db, 0, 5):
        return "nightly"
    return preset


__all__ = [
    "SAFE_HOUR",
    "SAFE_MINUTE",
    "boundary_splits_window",
    "captures_continuously",
    "describe_period",
    "parse_cron_time",
    "realign_cron",
    "safe_boundary",
]
