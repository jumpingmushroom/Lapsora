"""Weather data service using Open-Meteo API."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)
CACHE_TTL = 600  # 10 minutes

_cache: dict[str, tuple[float, float, int]] = {}  # key -> (timestamp, temp, code)

WMO_CODES: dict[int, str] = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Light Freezing Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Light Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ Hail",
    99: "Heavy Thunderstorm",
}


async def get_current_weather(lat: float, lon: float) -> tuple[float, int] | None:
    """Fetch current temperature and weather code from Open-Meteo.

    Returns (temperature_celsius, weather_code) or None on failure.
    Uses a 10-minute cache to avoid excessive API calls.
    """
    cache_key = f"{lat:.4f},{lon:.4f}"
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1], cached[2]

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]
            temp = float(current["temperature_2m"])
            code = int(current["weather_code"])
            _cache[cache_key] = (now, temp, code)
            return temp, code
    except Exception:
        logger.warning("Failed to fetch weather for %s,%s", lat, lon, exc_info=True)
        return None


def format_weather_text(temp: float, code: int, unit: str = "C") -> str:
    """Format weather data as display text."""
    label = WMO_CODES.get(code, "Unknown")
    if unit.upper() == "F":
        temp = temp * 9 / 5 + 32
        return f"{temp:.1f}\u00b0F {label}"
    return f"{temp:.1f}\u00b0C {label}"
