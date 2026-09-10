"""Standard-cron -> APScheduler translation for schedule expressions.

Schedules are stored as 5-field cron strings and are written by users (and by
the UI's presets) with ordinary Vixie-cron semantics. APScheduler's
``CronTrigger`` accepts the same field *layout* but a different day-of-week
dialect, so the two disagree about which day a stored expression means.
"""

# Standard cron numbers the week from Sunday; APScheduler numbers it from
# Monday. Day *names* mean the same thing in both dialects, which makes them a
# safe intermediate representation.
_DOW_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def normalize_cron_day_of_week(field: str) -> str:
    """Rewrite a standard-cron day-of-week field into APScheduler's dialect.

    Numeric tokens are expanded into an explicit list of day names, which
    sidesteps three incompatibilities at once: APScheduler's week starts on
    Monday, it rejects 7 as an alias for Sunday, and it refuses ranges that
    wrap past the end of its week (``fri-mon``). Tokens that are already names,
    or a bare ``*``, are passed through untouched.
    """
    days: list[int] = []
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise ValueError(f"Empty day-of-week value in {field!r}")
        # Names and a bare '*' already mean the same thing in both dialects.
        if not any(ch.isdigit() for ch in token):
            return field
        expr, sep, step_text = token.partition("/")
        step = int(step_text) if sep else 1
        if step < 1:
            raise ValueError(f"Day-of-week step must be positive in {token!r}")
        if expr == "*":
            first, span = 0, 7
        elif "-" in expr:
            start_text, _, end_text = expr.partition("-")
            first, last = _parse_dow(start_text), _parse_dow(end_text)
            # Standard cron allows a range to wrap (fri-mon); walk forwards
            # from `first` until `last` is reached rather than assuming order.
            span = (last - first) % 7 + 1
        else:
            first, span = _parse_dow(expr), 1
        days.extend((first + offset) % 7 for offset in range(0, span, step))

    # Preserve order while dropping duplicates, so '0,sun' collapses cleanly.
    return ",".join(dict.fromkeys(_DOW_NAMES[day] for day in days))


def _parse_dow(text: str) -> int:
    """Parse a single standard-cron day number (0-7, where both 0 and 7 mean Sunday)."""
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"Invalid day-of-week value {text!r}") from None
    if not 0 <= value <= 7:
        raise ValueError(f"Day-of-week value {value} is out of range (0-7)")
    return value % 7


def cron_trigger_kwargs(expr: str) -> dict[str, str]:
    """Split a 5-field cron expression into ``CronTrigger``/``add_job`` kwargs.

    Raises ValueError if the expression is not five fields or its day-of-week
    field is malformed; other field errors surface from APScheduler itself.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron expression must have 5 fields")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": normalize_cron_day_of_week(parts[4]),
    }
