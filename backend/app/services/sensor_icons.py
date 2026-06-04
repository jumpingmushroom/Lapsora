"""Curated multicolor sensor icons for Home Assistant overlays."""

import os

ICON_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sensor_icons")

# Stable icon keys exposed to the UI picker. Must match fetch_sensor_icons.sh.
_KEYS = ("thermometer", "humidity", "water", "wind", "power", "light", "battery", "gauge")


def available_icons() -> list[str]:
    """Icon keys for the picker."""
    return list(_KEYS)


def icon_path_for(key: str | None) -> str | None:
    """Absolute path to the icon PNG for `key`, or None if unknown/missing."""
    if not key or key not in _KEYS:
        return None
    path = os.path.join(ICON_DIR, f"{key}.png")
    return path if os.path.exists(path) else None
