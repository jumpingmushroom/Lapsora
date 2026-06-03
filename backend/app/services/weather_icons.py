"""Map WMO weather codes (+ day/night) to bundled multicolor icon files."""

import os

ICON_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "weather_icons")

# code -> (icon_base, has_day_night_variants)
_MAP: dict[int, tuple[str, bool]] = {
    0: ("clear", True),
    1: ("partly-cloudy", True),
    2: ("partly-cloudy", True),
    3: ("overcast", True),
    45: ("fog", True),
    48: ("fog", True),
    51: ("drizzle", False),
    53: ("drizzle", False),
    55: ("drizzle", False),
    56: ("sleet", False),
    57: ("sleet", False),
    61: ("rain", False),
    63: ("rain", False),
    65: ("rain", False),
    66: ("sleet", False),
    67: ("sleet", False),
    71: ("snow", False),
    73: ("snow", False),
    75: ("snow", False),
    77: ("snow", False),
    80: ("rain", False),
    81: ("rain", False),
    82: ("rain", False),
    85: ("snow", False),
    86: ("snow", False),
    95: ("thunderstorms", False),
    96: ("thunderstorms", False),
    99: ("thunderstorms", False),
}

_FALLBACK = ("overcast", False)


def icon_name_for(code: int, is_day: bool | None) -> str:
    """Return the icon basename (without extension) for a WMO code + day/night."""
    base, has_dn = _MAP.get(code, _FALLBACK)
    if has_dn:
        suffix = "day" if (is_day is None or is_day) else "night"
        return f"{base}-{suffix}"
    return base


def icon_path_for(code: int, is_day: bool | None) -> str | None:
    """Return the absolute path to the icon PNG, or None if missing on disk."""
    path = os.path.normpath(os.path.join(ICON_DIR, icon_name_for(code, is_day) + ".png"))
    return path if os.path.exists(path) else None
