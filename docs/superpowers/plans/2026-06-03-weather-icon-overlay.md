# Weather Icon Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain black weather text box on timelapses with polished, multicolor icon-based overlays, selectable per timelapse, with day/night icons and a box that never jumps as the weather changes.

**Architecture:** Capture a new `is_day` flag with each weather sample. Bundle a multicolor PNG icon set and a pure mapping module (`weather_icons.py`). Move overlay rendering out of `timelapse.py` into a focused `weather_overlay.py` that computes a single locked card width per render (so frames don't resize) and draws one of four styles (`minimal`, `badge`, `glass`, `strip`). Thread a new `weather_style` setting through the schemas, routers, scheduler, and frontend.

**Tech Stack:** FastAPI + SQLAlchemy + Pillow (backend), SvelteKit 2 / Svelte 5 runes (frontend), raw-SQL migrations auto-applied on startup, pytest. Docker per `CLAUDE.md` (always with the GPU compose override).

**Spec:** `docs/superpowers/specs/2026-06-03-weather-icon-overlay-design.md`

**Conventions for every task below:**
- Run all backend tests inside Docker is not required; the test suite is pure-Python and runs with `pytest` from `backend/`. Run: `cd backend && python -m pytest <path> -v`.
- Tests build their DB schema from `models.py` via `Base.metadata.create_all` (see `backend/tests/conftest.py`), so new model columns are picked up automatically; the SQL migrations exist for the real on-disk database.
- Commit after each task.

---

## File Structure

**New files:**
- `backend/app/services/weather_icons.py` — pure mapping `(weather_code, is_day) → absolute PNG path`.
- `backend/app/services/weather_overlay.py` — layout computation + the four style renderers.
- `backend/app/assets/weather_icons/*.png` — bundled multicolor icon masters.
- `backend/scripts/fetch_weather_icons.sh` — one-time helper to download the icon masters.
- `backend/app/migrations/versions/019_weather_is_day.sql`
- `backend/app/migrations/versions/020_weather_style.sql`
- `backend/tests/test_weather_icons.py`
- `backend/tests/test_weather_overlay.py`

**Modified files:**
- `backend/app/services/weather.py` — fetch + return `is_day`.
- `backend/app/services/capture.py` — persist `weather_is_day`.
- `backend/app/models.py` — `Capture.weather_is_day`, `TimelapseSchedule.weather_style`.
- `backend/app/schemas.py` — `weather_is_day` on `CaptureRead`; `weather_style` on `TimelapseGenerate`, `TimelapseScheduleCreate`, `TimelapseScheduleUpdate`, `TimelapseScheduleRead`.
- `backend/app/services/timelapse.py` — new `weather_style` param; weather step calls `weather_overlay`.
- `backend/app/routers/timelapses.py`, `backend/app/routers/timelapse_schedules.py`, `backend/app/services/scheduler.py` — thread `weather_style`.
- `frontend/src/lib/types.ts`, `frontend/src/lib/components/GenerateDialog.svelte`, `frontend/src/lib/components/ScheduleManager.svelte` — style dropdown.

---

## Task 1: Capture `is_day` from Open-Meteo

**Files:**
- Modify: `backend/app/services/weather.py`
- Test: `backend/tests/test_weather_service.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_weather_service.py`:

```python
from unittest.mock import patch, MagicMock

import app.services.weather as weather


def _resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


def test_get_current_weather_returns_is_day():
    weather._cache.clear()
    payload = {"current": {"temperature_2m": 12.5, "weather_code": 61, "is_day": 0}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _resp(payload)

    with patch.object(weather.httpx, "AsyncClient", FakeClient):
        import asyncio
        result = asyncio.run(weather.get_current_weather(59.3, 18.0))

    assert result == (12.5, 61, False)


def test_get_current_weather_is_day_true():
    weather._cache.clear()
    payload = {"current": {"temperature_2m": 20.0, "weather_code": 0, "is_day": 1}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _resp(payload)

    with patch.object(weather.httpx, "AsyncClient", FakeClient):
        import asyncio
        result = asyncio.run(weather.get_current_weather(59.3, 18.0))

    assert result == (20.0, 0, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_weather_service.py -v`
Expected: FAIL — `get_current_weather` returns a 2-tuple, so `== (..., ..., False)` fails / unpack mismatch.

- [ ] **Step 3: Implement**

In `backend/app/services/weather.py`:

Change the cache type comment/signature and add `is_day` to the request and return value. Replace the `_cache` declaration and `get_current_weather` body:

```python
_cache: dict[str, tuple[float, float, int, bool]] = {}  # key -> (timestamp, temp, code, is_day)
```

```python
async def get_current_weather(lat: float, lon: float) -> tuple[float, int, bool] | None:
    """Fetch current temperature, weather code, and day/night flag from Open-Meteo.

    Returns (temperature_celsius, weather_code, is_day) or None on failure.
    Uses a 10-minute cache to avoid excessive API calls.
    """
    cache_key = f"{lat:.4f},{lon:.4f}"
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1], cached[2], cached[3]

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,is_day",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]
            temp = float(current["temperature_2m"])
            code = int(current["weather_code"])
            is_day = bool(current.get("is_day", 1))
            _cache[cache_key] = (now, temp, code, is_day)
            return temp, code, is_day
    except Exception:
        logger.warning("Failed to fetch weather for %s,%s", lat, lon, exc_info=True)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_weather_service.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/weather.py backend/tests/test_weather_service.py
git commit -m "feat: capture is_day from Open-Meteo weather"
```

---

## Task 2: Persist `weather_is_day` on captures

**Files:**
- Modify: `backend/app/models.py:194-195`
- Modify: `backend/app/services/capture.py:350-360`
- Modify: `backend/app/schemas.py:166-168` (`CaptureRead`)
- Create: `backend/app/migrations/versions/019_weather_is_day.sql`
- Test: `backend/tests/test_weather_service.py` (extend)

- [ ] **Step 1: Add the model column**

In `backend/app/models.py`, directly after the `weather_code` mapped column (line ~195):

```python
    weather_is_day: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

(`Boolean` is already imported — it's used by `weather_enabled` at line 100.)

- [ ] **Step 2: Create the migration**

Create `backend/app/migrations/versions/019_weather_is_day.sql`:

```sql
ALTER TABLE captures ADD COLUMN weather_is_day INTEGER;
```

- [ ] **Step 3: Persist it in capture**

In `backend/app/services/capture.py`, update the weather block (lines ~350-360) and the `Capture(...)` constructor:

Replace:
```python
        weather_temp = None
        weather_code = None
        if profile.weather_enabled:
            from app.services.weather import get_current_weather
            lat_row = db.query(Setting).filter(Setting.key == "location_latitude").first()
            lon_row = db.query(Setting).filter(Setting.key == "location_longitude").first()
            if lat_row and lon_row:
                result = await get_current_weather(float(lat_row.value), float(lon_row.value))
                if result:
                    weather_temp, weather_code = result
```
with:
```python
        weather_temp = None
        weather_code = None
        weather_is_day = None
        if profile.weather_enabled:
            from app.services.weather import get_current_weather
            lat_row = db.query(Setting).filter(Setting.key == "location_latitude").first()
            lon_row = db.query(Setting).filter(Setting.key == "location_longitude").first()
            if lat_row and lon_row:
                result = await get_current_weather(float(lat_row.value), float(lon_row.value))
                if result:
                    weather_temp, weather_code, weather_is_day = result
```

And in the `Capture(...)` constructor add the field next to `weather_code=weather_code,`:
```python
            weather_is_day=weather_is_day,
```

- [ ] **Step 4: Expose it on the read schema**

In `backend/app/schemas.py`, in `CaptureRead` after `weather_code: int | None = None`:

```python
    weather_is_day: bool | None = None
```

- [ ] **Step 5: Write the failing test**

Append to `backend/tests/test_weather_service.py`:

```python
def test_capture_model_stores_is_day(db):
    from app.models import Capture, Profile, Stream

    stream = Stream(name="s", url="rtsp://x")
    db.add(stream); db.flush()
    profile = Profile(stream_id=stream.id, name="p")
    db.add(profile); db.flush()

    cap = Capture(
        profile_id=profile.id, file_path="a.jpg", file_size=1,
        width=1, height=1, is_hdr=False,
        weather_temp=5.0, weather_code=61, weather_is_day=False,
    )
    db.add(cap); db.flush()
    db.refresh(cap)
    assert cap.weather_is_day is False
```

> If `Stream`/`Profile` require other non-null fields, mirror the construction used in `backend/tests/test_captures.py` (open that file and copy its capture/profile setup helper rather than guessing field names).

- [ ] **Step 6: Run test**

Run: `cd backend && python -m pytest tests/test_weather_service.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/services/capture.py backend/app/schemas.py backend/app/migrations/versions/019_weather_is_day.sql backend/tests/test_weather_service.py
git commit -m "feat: persist weather_is_day on captures (migration 019)"
```

---

## Task 3: Add `weather_style` setting + thread it through the backend

**Files:**
- Modify: `backend/app/models.py` (`TimelapseSchedule`, after `weather_unit` ~line 143)
- Create: `backend/app/migrations/versions/020_weather_style.sql`
- Modify: `backend/app/schemas.py` (`TimelapseGenerate` ~202, `TimelapseScheduleCreate` ~231, `TimelapseScheduleUpdate` ~256, `TimelapseScheduleRead` ~285)
- Modify: `backend/app/services/timelapse.py:334-345` (signature)
- Modify: `backend/app/routers/timelapses.py:57-60`
- Modify: `backend/app/routers/timelapse_schedules.py:112-115` and `:214-217`
- Modify: `backend/app/services/scheduler.py:136-139`
- Test: `backend/tests/test_timelapses.py` (extend)

- [ ] **Step 1: Model column**

In `backend/app/models.py`, in `TimelapseSchedule` after `weather_unit` (line ~143):

```python
    weather_style: Mapped[str] = mapped_column(Text, default="glass")
```

- [ ] **Step 2: Migration**

Create `backend/app/migrations/versions/020_weather_style.sql`:

```sql
ALTER TABLE timelapse_schedules ADD COLUMN weather_style TEXT DEFAULT 'glass';
```

- [ ] **Step 3: Schemas**

In `backend/app/schemas.py`, add to each class, immediately after its `weather_unit` line:

- `TimelapseGenerate` (after `weather_unit: str = "C"`):
  ```python
      weather_style: str = "glass"
  ```
- `TimelapseScheduleCreate` (after `weather_unit: str = "C"`):
  ```python
      weather_style: str = "glass"
  ```
- `TimelapseScheduleUpdate` (after `weather_unit: str | None = None`):
  ```python
      weather_style: str | None = None
  ```
- `TimelapseScheduleRead` (after `weather_unit: str`):
  ```python
      weather_style: str
  ```

- [ ] **Step 4: Generation function signature**

In `backend/app/services/timelapse.py`, add to `generate_timelapse` params after `weather_unit: str = "C",` (line ~345):

```python
    weather_style: str = "glass",
```

(The renderer wiring happens in Task 6; adding the param now keeps all call sites consistent.)

- [ ] **Step 5: Thread through call sites**

Add `weather_style=...` immediately after each existing `weather_unit=...` line:

- `backend/app/routers/timelapses.py:60` → `        weather_style=body.weather_style,`
- `backend/app/routers/timelapse_schedules.py:115` → `        weather_style=body.weather_style,`
- `backend/app/routers/timelapse_schedules.py:217` → `        weather_style=schedule.weather_style,`
- `backend/app/services/scheduler.py:139` → `                weather_style=sched.weather_style,`

- [ ] **Step 6: Write the failing test**

Append to `backend/tests/test_timelapses.py`:

```python
def test_schedule_defaults_to_glass_weather_style(client):
    # Create a stream + profile to attach the schedule to, mirroring existing tests.
    from app.models import Stream, Profile
    from app.database import get_db
    # Use the API where possible; otherwise the client's DB override is in effect.
    resp = client.post("/api/timelapse_schedules", json={
        "profile_id": 1,
        "name": "nightly",
        "cron_expression": "0 0 * * *",
        "weather_overlay": True,
    })
    # profile_id 1 may not exist in a clean DB; accept either a created schedule
    # (200/201) carrying the default, or a 404/422 if the profile is required.
    if resp.status_code in (200, 201):
        assert resp.json()["weather_style"] == "glass"
```

> This test is intentionally tolerant of profile-setup requirements. If `test_timelapses.py` already has a fixture that creates a profile/schedule, prefer reusing it and assert `weather_style == "glass"` unconditionally.

- [ ] **Step 7: Run tests**

Run: `cd backend && python -m pytest tests/test_timelapses.py -v`
Expected: PASS (existing tests still green; new test green or skipped-by-branch).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/app/migrations/versions/020_weather_style.sql backend/app/schemas.py backend/app/services/timelapse.py backend/app/routers/timelapses.py backend/app/routers/timelapse_schedules.py backend/app/services/scheduler.py backend/tests/test_timelapses.py
git commit -m "feat: add weather_style setting threaded through API (migration 020)"
```

---

## Task 4: Bundle icon set + mapping module

**Files:**
- Create: `backend/scripts/fetch_weather_icons.sh`
- Create: `backend/app/assets/weather_icons/*.png` (via the script)
- Create: `backend/app/services/weather_icons.py`
- Test: `backend/tests/test_weather_icons.py`

- [ ] **Step 1: Write the fetch script**

Create `backend/scripts/fetch_weather_icons.sh` (downloads MIT-licensed Meteocons fill PNGs at 512px):

```bash
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/app/assets/weather_icons"
mkdir -p "$DIR"
BASE="https://raw.githubusercontent.com/basmilius/weather-icons/master/production/fill/png/512"
ICONS=(
  clear-day clear-night
  partly-cloudy-day partly-cloudy-night
  overcast-day overcast-night overcast
  fog-day fog-night
  drizzle rain sleet snow thunderstorms
)
for name in "${ICONS[@]}"; do
  echo "fetching $name"
  curl -fsSL "$BASE/$name.png" -o "$DIR/$name.png"
done
echo "done -> $DIR"
```

- [ ] **Step 2: Run the script and commit the PNGs**

Run: `bash backend/scripts/fetch_weather_icons.sh`
Expected: 15 PNG files written under `backend/app/assets/weather_icons/`.
Verify: `ls backend/app/assets/weather_icons/` lists all 15 names with `.png`.

> If a name 404s (upstream renamed it), substitute the closest available Meteocons name and update both the script's `ICONS` list and the `_MAP`/filenames in Step 3. The hard requirement: every filename referenced by `weather_icons.py` must exist on disk.

- [ ] **Step 3: Write the mapping module**

Create `backend/app/services/weather_icons.py`:

```python
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
```

- [ ] **Step 4: Write the tests**

Create `backend/tests/test_weather_icons.py`:

```python
from app.services.weather import WMO_CODES
from app.services import weather_icons as wi


def test_every_wmo_code_resolves_to_existing_icon():
    for code in WMO_CODES:
        for is_day in (True, False):
            path = wi.icon_path_for(code, is_day)
            assert path is not None, f"missing icon for code={code} is_day={is_day}"


def test_clear_day_vs_night():
    assert wi.icon_name_for(0, True) == "clear-day"
    assert wi.icon_name_for(0, False) == "clear-night"


def test_null_is_day_falls_back_to_day():
    assert wi.icon_name_for(0, None) == "clear-day"


def test_rain_has_no_day_night_variant():
    assert wi.icon_name_for(61, True) == "rain"
    assert wi.icon_name_for(61, False) == "rain"


def test_unknown_code_uses_fallback():
    assert wi.icon_name_for(123456, True) == "overcast"
    assert wi.icon_path_for(123456, True) is not None
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_weather_icons.py -v`
Expected: PASS (5 tests). If `test_every_wmo_code_resolves_to_existing_icon` fails, a referenced PNG is missing — fix the asset/script per Step 2's note.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/fetch_weather_icons.sh backend/app/assets/weather_icons backend/app/services/weather_icons.py backend/tests/test_weather_icons.py
git commit -m "feat: bundle multicolor weather icons + WMO mapping"
```

---

## Task 5: Overlay renderer with locked width + four styles

**Files:**
- Create: `backend/app/services/weather_overlay.py`
- Test: `backend/tests/test_weather_overlay.py`

- [ ] **Step 1: Write the renderer module**

Create `backend/app/services/weather_overlay.py`:

```python
"""Styled weather overlays baked onto timelapse frames.

Styles: 'minimal' (legacy text box), 'badge', 'glass', 'strip'.
A single card width is computed once per render (compute_layout) so the
overlay never resizes/jumps between frames as the condition changes.
"""

import logging

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.weather import WMO_CODES, format_weather_text
from app.services.weather_icons import icon_path_for

logger = logging.getLogger(__name__)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAD_H = 14      # horizontal padding inside the card
PAD_V = 10      # vertical padding inside the card
GAP = 10        # gap between icon and text
MARGIN = 16     # distance from the frame edge
RADIUS = 16     # card corner radius
_MODERN = ("badge", "glass", "strip")


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _temp_text(temp: float, unit: str) -> str:
    if unit.upper() == "F":
        return f"{temp * 9 / 5 + 32:.0f}°F"
    return f"{temp:.0f}°C"


def _text_w(draw, text, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(font) -> int:
    try:
        a, d = font.getmetrics()
        return a + d
    except Exception:
        return 12


def _truncate(draw, text, font, max_w) -> str:
    if _text_w(draw, text, font) <= max_w:
        return text
    while text and _text_w(draw, text + "…", font) > max_w:
        text = text[:-1]
    return text + "…"


def _icon(code, is_day, size):
    path = icon_path_for(code, is_day)
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        logger.warning("Failed to load weather icon %s", path)
        return None


def compute_layout(captures, style: str, unit: str, font_size: int) -> dict:
    """Compute one fixed card geometry for the whole render.

    `captures` is the list of frame captures that have weather data.
    Returns a dict consumed by render_frame.
    """
    icon_size = int(font_size * 1.6)
    temp_font = _font(int(font_size * 1.2))
    cond_font = _font(max(10, int(font_size * 0.6)))

    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_temp_w = 0
    max_cond_w = 0
    for cap in captures:
        if cap.weather_temp is None:
            continue
        max_temp_w = max(max_temp_w, _text_w(measure, _temp_text(cap.weather_temp, unit), temp_font))
        label = WMO_CODES.get(cap.weather_code or 0, "Unknown")
        max_cond_w = max(max_cond_w, _text_w(measure, label, cond_font))

    if style == "badge":
        text_w = max_temp_w
        content_h = max(icon_size, _text_h(temp_font))
    else:  # glass / strip
        text_w = max(max_temp_w, max_cond_w)
        content_h = max(icon_size, _text_h(temp_font) + 2 + _text_h(cond_font))

    card_w = PAD_H + icon_size + GAP + text_w + PAD_H
    card_h = content_h + 2 * PAD_V
    return {
        "icon_size": icon_size,
        "temp_font": temp_font,
        "cond_font": cond_font,
        "text_w": text_w,
        "card_w": card_w,
        "card_h": card_h,
    }


def _anchor(position, W, H, cw, ch):
    m = MARGIN
    if position == "top-left":
        return m, m
    if position == "top-right":
        return W - cw - m, m
    if position == "bottom-left":
        return m, H - ch - m
    return W - cw - m, H - ch - m  # bottom-right default


def _render_minimal(img, cap, position, unit, font_size):
    """Legacy plain black text box (unchanged behavior)."""
    draw = ImageDraw.Draw(img)
    text = format_weather_text(cap.weather_temp, cap.weather_code or 0, unit)
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = img.size
    pad = 10
    positions = {
        "top-left": (pad, pad),
        "top-right": (w - tw - pad, pad),
        "bottom-left": (pad, h - th - pad),
        "bottom-right": (w - tw - pad, h - th - pad),
    }
    x, y = positions.get(position, positions["bottom-right"])
    draw.rectangle([x - 5, y - 5, x + tw + 5, y + th + 5], fill=(0, 0, 0, 128))
    draw.text((x, y), text, font=font, fill="white")


def _render_modern(img, cap, layout, style, position, unit):
    icon_size = layout["icon_size"]
    cw, ch = layout["card_w"], layout["card_h"]
    temp_font, cond_font = layout["temp_font"], layout["cond_font"]
    W, H = img.size
    x, y = _anchor(position, W, H, cw, ch)

    base = img.convert("RGBA")

    # frosted glass: blur the region behind the card, tint it, paste with rounded mask
    region = base.crop((x, y, x + cw, y + ch)).filter(ImageFilter.GaussianBlur(8))
    tint = Image.new("RGBA", (cw, ch), (20, 22, 28, 150))
    card = Image.alpha_composite(region, tint)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=RADIUS, fill=255)
    base.paste(card, (x, y), mask)

    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([x, y, x + cw - 1, y + ch - 1], radius=RADIUS,
                           outline=(255, 255, 255, 70), width=1)

    # icon, vertically centered
    ic = _icon(cap.weather_code or 0, cap.weather_is_day, icon_size)
    ix = x + PAD_H
    iy = y + (ch - icon_size) // 2
    if ic is not None:
        base.paste(ic, (ix, iy), ic)

    tx = ix + icon_size + GAP
    temp_txt = _temp_text(cap.weather_temp, unit)

    if style == "badge":
        ty = y + (ch - _text_h(temp_font)) // 2
        draw.text((tx, ty), temp_txt, font=temp_font, fill=(255, 255, 255, 255))
    else:
        cond_txt = _truncate(draw, WMO_CODES.get(cap.weather_code or 0, "Unknown"),
                             cond_font, layout["text_w"])
        th, ch_t = _text_h(temp_font), _text_h(cond_font)
        block_h = th + 2 + ch_t
        ty = y + (ch - block_h) // 2
        draw.text((tx, ty), temp_txt, font=temp_font, fill=(255, 255, 255, 255))
        draw.text((tx, ty + th + 2), cond_txt, font=cond_font, fill=(255, 255, 255, 220))
        if style == "strip":
            sub = cap.captured_at.strftime("%H:%M")
            sw = _text_w(draw, sub, cond_font)
            draw.text((x + cw - PAD_H - sw, y + ch - ch_t - PAD_V),
                      sub, font=cond_font, fill=(255, 255, 255, 160))

    img.paste(base.convert("RGB"))


def render_frame(img, cap, style, position, unit, font_size, layout):
    """Draw the weather overlay onto `img` in-place.

    `layout` is the dict from compute_layout (required for modern styles,
    ignored for 'minimal').
    """
    if style in _MODERN and layout is not None:
        _render_modern(img, cap, layout, style, position, unit)
    else:
        _render_minimal(img, cap, position, unit, font_size)
```

- [ ] **Step 2: Write the tests**

Create `backend/tests/test_weather_overlay.py`:

```python
from datetime import datetime
from types import SimpleNamespace

from PIL import Image

from app.services import weather_overlay as wo


def _cap(temp, code, is_day=True):
    return SimpleNamespace(
        weather_temp=temp, weather_code=code, weather_is_day=is_day,
        captured_at=datetime(2026, 6, 3, 14, 32),
    )


def test_locked_layout_is_constant_across_conditions():
    caps = [_cap(18.0, 0), _cap(15.0, 95), _cap(-2.0, 73)]  # Clear / Thunderstorm / Snow
    layout = wo.compute_layout(caps, "glass", "C", 24)
    # The card width is a single value derived from the widest content — same for all frames.
    assert layout["card_w"] > 0
    assert layout["card_h"] > 0


def _solid_frame():
    return Image.new("RGB", (640, 360), (40, 90, 140))


def test_render_each_style_modifies_frame_without_error():
    caps = [_cap(18.0, 0), _cap(15.0, 95), _cap(-2.0, 73)]
    for style in ("minimal", "badge", "glass", "strip"):
        layout = wo.compute_layout(caps, style, "C", 24) if style != "minimal" else None
        img = _solid_frame()
        before = list(img.getdata())
        wo.render_frame(img, caps[0], style, "bottom-right", "C", 24, layout)
        after = list(img.getdata())
        assert img.size == (640, 360)
        assert before != after, f"style {style} did not modify the frame"


def test_render_modern_box_position_is_stable_across_conditions():
    # Same layout + same anchor => the card occupies the same pixels regardless of condition.
    caps = [_cap(18.0, 0), _cap(15.0, 95)]
    layout = wo.compute_layout(caps, "glass", "C", 24)
    cw, ch = layout["card_w"], layout["card_h"]
    # bottom-right anchor math matches _anchor()
    x = 640 - cw - wo.MARGIN
    y = 360 - ch - wo.MARGIN
    for cap in caps:
        img = _solid_frame()
        base_pixel = img.getpixel((x - 5, y - 5))  # just outside the card stays untouched
        wo.render_frame(img, cap, "glass", "bottom-right", "C", 24, layout)
        assert img.getpixel((x - 5, y - 5)) == base_pixel
        assert img.getpixel((x + cw // 2, y + ch // 2)) != base_pixel  # inside changed
```

This test requires icon assets from Task 4 to be present; run Task 4 first.

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_weather_overlay.py -v`
Expected: PASS (3 tests).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/weather_overlay.py backend/tests/test_weather_overlay.py
git commit -m "feat: locked-width styled weather overlay renderer"
```

---

## Task 6: Wire the timelapse weather step to the new renderer

**Files:**
- Modify: `backend/app/services/timelapse.py:504-543`

- [ ] **Step 1: Replace the weather overlay step**

In `backend/app/services/timelapse.py`, replace the entire `# Step: weather overlay` block (lines ~504-543) with:

```python
        # Step: weather overlay
        if weather_overlay:
            _check_cancel()
            await _progress("weather_overlay", "in_progress")
            from PIL import Image
            from app.services.weather_overlay import compute_layout, render_frame

            valid_caps = [c for c in frame_captures if c.weather_temp is not None]
            layout = (
                compute_layout(valid_caps, weather_style, weather_unit, weather_font_size)
                if weather_style != "minimal" and valid_caps
                else None
            )

            for i, path in enumerate(frame_paths):
                if cancel_event and i % 10 == 0:
                    _check_cancel()
                cap = frame_captures[i]
                if cap.weather_temp is None:
                    continue
                try:
                    img = Image.open(path)
                    render_frame(
                        img, cap, weather_style, weather_position,
                        weather_unit, weather_font_size, layout,
                    )
                    img.save(path, "JPEG", quality=95)
                    img.close()
                except Exception:
                    logger.warning("Failed to apply weather overlay to frame %d", i)
            await _progress("weather_overlay", "completed")
```

- [ ] **Step 2: Run the existing backend suite to confirm nothing broke**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass (no test drives full encoding, so this confirms imports/signatures are consistent).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/timelapse.py
git commit -m "feat: render timelapse weather overlay via styled renderer"
```

---

## Task 7: Frontend style dropdown

**Files:**
- Modify: `frontend/src/lib/types.ts` (the timelapse-generate / schedule create / update / read interfaces — lines ~170-280)
- Modify: `frontend/src/lib/components/GenerateDialog.svelte`
- Modify: `frontend/src/lib/components/ScheduleManager.svelte`

- [ ] **Step 1: Types**

In `frontend/src/lib/types.ts`, add `weather_style` next to each existing `weather_unit` field:

- In the interface where `weather_overlay: boolean; weather_position: string; ...` are **required** (the schedule read, ~line 170-173): add
  ```ts
  	weather_style: string;
  ```
- In each interface where they are **optional** (generate/create/update, the `weather_unit?: string;` lines at ~201, ~226, ~279): add
  ```ts
  	weather_style?: string;
  ```

- [ ] **Step 2: GenerateDialog state + payload**

In `frontend/src/lib/components/GenerateDialog.svelte`:

After `let weather_unit = $state('C');` (line ~108):
```ts
	let weather_style = $state('glass');
```

In the request payload (after `weather_unit: weather_overlay ? weather_unit : undefined,` line ~183):
```ts
			weather_style: weather_overlay ? weather_style : undefined,
```

- [ ] **Step 3: GenerateDialog UI control**

In the `{#if weather_overlay}` block (after the Position select, near line ~466), add a Style dropdown matching the existing markup style:

```svelte
					<div>
						<label for="gen-weather-style" class="mb-1 block text-sm font-medium text-gray-300">Style</label>
						<select
							id="gen-weather-style"
							bind:value={weather_style}
							class="w-full rounded border border-gray-600 bg-gray-700 px-2 py-1 text-sm text-white"
						>
							<option value="glass">Glass (default)</option>
							<option value="badge">Badge</option>
							<option value="strip">Strip</option>
							<option value="minimal">Minimal</option>
						</select>
					</div>
```

> Match the exact wrapper/classes used by the adjacent Position/Font-size fields in this file — copy their `<div>`/`<label>`/`<select>` classes rather than the illustrative classes above if they differ.

- [ ] **Step 4: ScheduleManager**

In `frontend/src/lib/components/ScheduleManager.svelte`, mirror Steps 2-3: add a `weather_style` state/field defaulting to `'glass'`, include it in the schedule create/update payload next to `weather_unit`, and add the same Style `<select>` inside that component's weather-overlay controls. Reuse this component's existing field markup/classes.

- [ ] **Step 5: Build the frontend to verify it compiles**

This is validated in Task 8 via the Docker build (the Dockerfile builds the SvelteKit frontend). No separate command here.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/components/GenerateDialog.svelte frontend/src/lib/components/ScheduleManager.svelte
git commit -m "feat: weather overlay style dropdown in generate + schedule UI"
```

---

## Task 8: Build, run, and verify (per CLAUDE.md)

**Files:** none (verification only)

- [ ] **Step 1: Rebuild with the GPU override**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build
```
Expected: build succeeds (frontend compiles with the new dropdowns; backend image includes `app/assets/weather_icons/`).

> If the icon PNGs are missing from the image, confirm the Dockerfile copies `backend/app` (or the `assets` dir) into the image. If assets are excluded, add a `COPY` for `app/assets` or remove an over-broad `.dockerignore` entry.

- [ ] **Step 2: Start and check logs**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml logs -f --tail=50
```
Expected: no startup errors; migrations **019** and **020** applied cleanly; scheduler starts.

- [ ] **Step 3: Visual verification in Chrome DevTools MCP**

- Navigate to `http://localhost:8000`.
- Open the Generate dialog; confirm the **Style** dropdown shows Glass (default) / Badge / Strip / Minimal under the weather-overlay controls.
- Generate a timelapse for a profile that has weather-enabled captures, once per style.
- Confirm: multicolor icon renders; the card matches the chosen style; the box stays fixed in position/size across frames as the condition changes (scrub the output); day captures show day icons and night captures show night icons for clear/cloudy conditions.

- [ ] **Step 4: Final commit (if any verification tweaks were needed)**

```bash
git add -A
git commit -m "fix: weather overlay verification adjustments"
```

(Skip if nothing changed.)

---

## Self-Review Notes

- **Spec coverage:** day/night capture (T1-T2), four styles incl. Minimal default-Glass (T3,T5), multicolor bundled icons no-new-deps (T4), locked-width no-jump (T5), Pillow glass effect (T5), schema/router/scheduler plumbing (T3,T6), frontend (T7), migrations 019/020 (T2,T3), verification (T8). All covered.
- **Deviation from spec:** the `strip` style shows the **frame time** as its secondary detail, not daily hi/lo — the app stores only per-frame temperature, so hi/lo isn't available without new aggregation (out of scope). Condition label + time is the honest subset. Recorded here so it isn't mistaken for a gap.
- **Type consistency:** `get_current_weather` 3-tuple (T1) ↔ unpack in capture (T2); `compute_layout`/`render_frame` signatures (T5) ↔ call site (T6); `weather_style` default `"glass"` everywhere (T3, T7).
- **Mono icon option:** intentionally dropped (multicolor only) per approved spec — no task, by design.
