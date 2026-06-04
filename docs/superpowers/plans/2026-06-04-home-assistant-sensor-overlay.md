# Home Assistant Sensor Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull Home Assistant sensor values per captured frame and overlay them on generated timelapses, configured via a new Integrations settings tab and a per-profile sensor picker.

**Architecture:** Mirrors the existing weather pipeline. Global HA connection (URL + encrypted token) lives in `settings`. At capture time each frame snapshots the profile's configured sensors into `captures.sensor_data` (JSON). At generation time a locked-width frosted-glass panel is rendered from those snapshots. The frosted-glass primitive is extracted from `weather_overlay.py` into a shared helper used by both overlays.

**Tech Stack:** FastAPI + SQLAlchemy + APScheduler (backend), Pillow (overlays), httpx (HA REST), SvelteKit 2 / Svelte 5 runes (frontend), raw-SQL migrations auto-applied at startup.

**Scope note vs spec:** The spec mentioned an `ha_overlay_style` field. This plan **drops it** (YAGNI) — there is exactly one sensor layout (the vertical glass panel chosen in brainstorming), so only `ha_overlay` (bool) and `ha_overlay_position` are threaded. Add a style field later if a second layout is ever introduced.

## Reference patterns (read before starting)

- Weather pipeline you are mirroring: `backend/app/services/weather.py`, `weather_overlay.py`, `weather_icons.py`; `captures.weather_*` columns in `backend/app/models.py`; weather threading in `backend/app/services/timelapse.py:334-535`, `routers/timelapse_schedules.py`, `services/generation_queue.py`, `services/scheduler.py`; weather schema fields in `backend/app/schemas.py`.
- Migration runner: `backend/app/migrations/runner.py` — applies `versions/*.sql` in sorted order, splits on `;`, tolerates "duplicate column name".
- Settings key/value pattern + `encrypt()`/`decrypt()`: `backend/app/routers/settings.py`, `backend/app/config.py`.
- Local backend pytest recipe (used in every test step below):
  ```bash
  cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
    LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
    python -m pytest -p no:cacheprovider -q <PATHS>
  ```
  A trailing `RuntimeError: <Queue …> bound to a different event loop` after the summary is harmless shutdown noise.

## File Structure

**Create:**
- `backend/app/migrations/versions/021_capture_sensor_data.sql`
- `backend/app/migrations/versions/022_profile_ha_sensors.sql`
- `backend/app/migrations/versions/023_schedule_ha_overlay.sql`
- `backend/app/services/homeassistant.py` — HA REST client + snapshot builder
- `backend/app/services/overlay_glass.py` — shared frosted-glass card primitive
- `backend/app/services/sensor_overlay.py` — sensor panel renderer
- `backend/app/services/sensor_icons.py` — curated icon key→path map
- `backend/scripts/fetch_sensor_icons.sh` — downloads the icon PNGs
- `backend/app/assets/sensor_icons/*.png` — curated multicolor icons
- `backend/tests/test_homeassistant.py`
- `backend/tests/test_sensor_icons.py`
- `backend/tests/test_sensor_overlay.py`
- `backend/tests/test_ha_overlay_schedules.py`

**Modify:**
- `backend/app/models.py` — new columns
- `backend/app/services/weather_overlay.py` — use shared glass helper
- `backend/app/services/capture.py` — snapshot sensors per frame
- `backend/app/services/timelapse.py` — render sensor overlay step
- `backend/app/services/generation_queue.py` — (no change needed; `**kwargs` passthrough — verify only)
- `backend/app/services/scheduler.py` — thread `ha_overlay`/`ha_overlay_position`
- `backend/app/routers/timelapse_schedules.py` — thread fields in create + trigger
- `backend/app/routers/timelapses.py` — thread fields in generate endpoint
- `backend/app/routers/settings.py` — HA endpoints
- `backend/app/schemas.py` — HA settings + timelapse/schedule/capture/profile fields
- `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- `frontend/src/routes/settings/+page.svelte` — tabs + Integrations
- `frontend/src/lib/components/ProfileForm.svelte` — HA sensors section
- `frontend/src/lib/components/GenerateDialog.svelte`, `ScheduleManager.svelte` — overlay controls

---

### Task 1: Migrations + model columns

**Files:**
- Create: `backend/app/migrations/versions/021_capture_sensor_data.sql`
- Create: `backend/app/migrations/versions/022_profile_ha_sensors.sql`
- Create: `backend/app/migrations/versions/023_schedule_ha_overlay.sql`
- Modify: `backend/app/models.py`

- [ ] **Step 1: Write the three migration files**

`021_capture_sensor_data.sql`:
```sql
ALTER TABLE captures ADD COLUMN sensor_data TEXT;
```

`022_profile_ha_sensors.sql`:
```sql
ALTER TABLE profiles ADD COLUMN ha_sensors TEXT;
```

`023_schedule_ha_overlay.sql`:
```sql
ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay BOOLEAN DEFAULT 0;
ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay_position TEXT DEFAULT 'top-left';
```

- [ ] **Step 2: Add model columns**

In `backend/app/models.py`, in `class Capture`, after the `weather_is_day` line:
```python
    sensor_data: Mapped[str | None] = mapped_column(Text, nullable=True)
```

In `class Profile`, after the existing `weather_enabled` column (search for `weather_enabled`), add:
```python
    ha_sensors: Mapped[str | None] = mapped_column(Text, nullable=True)
```

In `class TimelapseSchedule`, after the `weather_style` column, add:
```python
    ha_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    ha_overlay_position: Mapped[str] = mapped_column(Text, default="top-left")
```

Confirm `Text` and `Boolean` are already imported at the top of `models.py` (they are — used by existing columns).

- [ ] **Step 3: Verify migrations apply by booting the app's migration runner**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -c "from app.database import engine; from app.migrations.runner import run_migrations; run_migrations(engine); print('OK')"
```
Expected: prints `OK`, logs show `Applying migration: 021_...`, `022_...`, `023_...` with no error.

- [ ] **Step 4: Commit**
```bash
git add backend/app/migrations/versions/021_capture_sensor_data.sql \
        backend/app/migrations/versions/022_profile_ha_sensors.sql \
        backend/app/migrations/versions/023_schedule_ha_overlay.sql \
        backend/app/models.py
git commit -m "feat: schema for HA sensor overlay (sensor_data, ha_sensors, ha_overlay)"
```

---

### Task 2: Home Assistant REST service

**Files:**
- Create: `backend/app/services/homeassistant.py`
- Test: `backend/tests/test_homeassistant.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_homeassistant.py`:
```python
import json
import pytest
from app.services import homeassistant as ha


def test_build_sensor_snapshot_merges_config_and_readings():
    sensors = json.dumps([
        {"entity_id": "sensor.temp", "label": "Greenhouse", "unit": "°C", "icon": "thermometer"},
        {"entity_id": "sensor.hum", "label": "Humidity", "unit": "%", "icon": "humidity"},
    ])
    readings = {
        "sensor.temp": {"value": "21.4", "unit": "°C"},
        "sensor.hum": {"value": "62", "unit": "%"},
    }
    out = json.loads(ha.build_sensor_snapshot(sensors, readings))
    assert out["sensor.temp"] == {"value": "21.4", "unit": "°C", "label": "Greenhouse", "icon": "thermometer"}
    assert out["sensor.hum"]["value"] == "62"


def test_build_sensor_snapshot_skips_missing_readings():
    sensors = json.dumps([{"entity_id": "sensor.temp", "label": "T", "unit": "°C", "icon": ""}])
    assert ha.build_sensor_snapshot(sensors, {}) is None


def test_build_sensor_snapshot_unit_falls_back_to_reading():
    sensors = json.dumps([{"entity_id": "sensor.temp", "label": "T", "unit": "", "icon": ""}])
    readings = {"sensor.temp": {"value": "5", "unit": "kWh"}}
    out = json.loads(ha.build_sensor_snapshot(sensors, readings))
    assert out["sensor.temp"]["unit"] == "kWh"


def test_build_sensor_snapshot_handles_bad_json():
    assert ha.build_sensor_snapshot("not json", {}) is None
    assert ha.build_sensor_snapshot(None, {}) is None


@pytest.mark.asyncio
async def test_list_sensor_entities_filters_and_shapes(monkeypatch):
    fake_states = [
        {"entity_id": "sensor.temp", "state": "21.4",
         "attributes": {"friendly_name": "Greenhouse", "unit_of_measurement": "°C", "device_class": "temperature"}},
        {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
        {"entity_id": "binary_sensor.door", "state": "off", "attributes": {"friendly_name": "Door"}},
    ]

    async def fake_get_states(base_url, token):
        return fake_states

    monkeypatch.setattr(ha, "get_states", fake_get_states)
    out = await ha.list_sensor_entities("http://x", "tok")
    ids = [e["entity_id"] for e in out]
    assert "sensor.temp" in ids and "binary_sensor.door" in ids
    assert "light.kitchen" not in ids
    temp = next(e for e in out if e["entity_id"] == "sensor.temp")
    assert temp["friendly_name"] == "Greenhouse"
    assert temp["unit"] == "°C"


@pytest.mark.asyncio
async def test_read_sensors_returns_value_and_unit(monkeypatch):
    async def fake_get_states(base_url, token):
        return [{"entity_id": "sensor.temp", "state": "21.4",
                 "attributes": {"unit_of_measurement": "°C"}}]
    monkeypatch.setattr(ha, "get_states", fake_get_states)
    out = await ha.read_sensors("http://x", "tok", ["sensor.temp", "sensor.missing"])
    assert out == {"sensor.temp": {"value": "21.4", "unit": "°C"}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_homeassistant.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.homeassistant'` / attribute errors.

- [ ] **Step 3: Write the implementation**

`backend/app/services/homeassistant.py`:
```python
"""Home Assistant integration: read sensor entity states via the REST API."""

import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)
CACHE_TTL = 15  # seconds — dedupe near-simultaneous per-profile captures
SENSOR_DOMAINS = ("sensor.", "binary_sensor.")

_cache: dict[str, tuple[float, list[dict]]] = {}  # base_url -> (ts, states)


def get_ha_config(db) -> tuple[str, str] | None:
    """Return (base_url, decrypted_token) from settings, or None if unset."""
    from app.config import decrypt
    from app.models import Setting

    url_row = db.query(Setting).filter(Setting.key == "ha_base_url").first()
    tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
    if not url_row or not url_row.value or not tok_row or not tok_row.value:
        return None
    try:
        token = decrypt(tok_row.value)
    except Exception:
        logger.warning("Failed to decrypt HA token")
        return None
    return url_row.value, token


async def get_states(base_url: str, token: str) -> list[dict] | None:
    """Fetch all entity states from HA. Cached briefly per base_url."""
    base = base_url.rstrip("/")
    now = time.time()
    cached = _cache.get(base)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{base}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            states = resp.json()
            _cache[base] = (now, states)
            return states
    except Exception:
        logger.warning("Failed to fetch HA states from %s", base, exc_info=True)
        return None


async def test_connection(base_url: str, token: str) -> dict:
    """Validate reachability + auth against HA's /api/ root."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{base}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            return {"success": True, "message": "Connected"}
        if resp.status_code == 401:
            return {"success": False, "message": "Unauthorized — check the access token"}
        return {"success": False, "message": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


async def list_sensor_entities(base_url: str, token: str) -> list[dict]:
    """Return picker-friendly sensor entities (sorted by friendly name)."""
    states = await get_states(base_url, token)
    if not states:
        return []
    out = []
    for s in states:
        eid = s.get("entity_id", "")
        if not eid.startswith(SENSOR_DOMAINS):
            continue
        attrs = s.get("attributes", {})
        out.append({
            "entity_id": eid,
            "friendly_name": attrs.get("friendly_name", eid),
            "unit": attrs.get("unit_of_measurement", ""),
            "device_class": attrs.get("device_class", ""),
        })
    out.sort(key=lambda e: e["friendly_name"].lower())
    return out


async def read_sensors(base_url: str, token: str, entity_ids: list[str]) -> dict[str, dict]:
    """Read current {value, unit} for each entity_id. Missing entities omitted."""
    states = await get_states(base_url, token)
    if not states:
        return {}
    by_id = {s.get("entity_id"): s for s in states}
    result: dict[str, dict] = {}
    for eid in entity_ids:
        s = by_id.get(eid)
        if not s:
            continue
        attrs = s.get("attributes", {})
        result[eid] = {"value": s.get("state"), "unit": attrs.get("unit_of_measurement", "")}
    return result


def build_sensor_snapshot(sensors_json: str | None, readings: dict[str, dict]) -> str | None:
    """Merge a profile's configured sensors with HA readings into a JSON snapshot
    suitable for storing in captures.sensor_data. Returns None if empty/invalid."""
    if not sensors_json:
        return None
    try:
        sensors = json.loads(sensors_json)
    except (json.JSONDecodeError, TypeError):
        return None
    snapshot: dict[str, dict] = {}
    for s in sensors:
        eid = s.get("entity_id")
        r = readings.get(eid) if eid else None
        if not eid or r is None:
            continue
        snapshot[eid] = {
            "value": r.get("value"),
            "unit": s.get("unit") or r.get("unit") or "",
            "label": s.get("label") or eid,
            "icon": s.get("icon") or "",
        }
    return json.dumps(snapshot) if snapshot else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run the same command as Step 2.
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/homeassistant.py backend/tests/test_homeassistant.py
git commit -m "feat: Home Assistant REST service (states, entities, snapshot)"
```

---

### Task 3: HA settings schemas + endpoints

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_homeassistant.py` (append endpoint tests)

- [ ] **Step 1: Write the failing endpoint tests**

Append to `backend/tests/test_homeassistant.py`:
```python
def test_ha_settings_roundtrip_masks_token(client):
    # Save URL + token
    resp = client.put("/api/settings/homeassistant",
                      json={"base_url": "http://ha.local:8123/", "token": "secret-token"})
    assert resp.status_code == 200, resp.text
    # GET never returns the token, reports connected
    got = client.get("/api/settings/homeassistant").json()
    assert got["base_url"] == "http://ha.local:8123"  # trailing slash stripped
    assert got["connected"] is True
    assert "token" not in got


def test_ha_settings_update_without_token_keeps_existing(client):
    client.put("/api/settings/homeassistant", json={"base_url": "http://a", "token": "tok1"})
    # Update URL only (no token) — should stay connected
    client.put("/api/settings/homeassistant", json={"base_url": "http://b"})
    got = client.get("/api/settings/homeassistant").json()
    assert got["base_url"] == "http://b"
    assert got["connected"] is True
```
(The `client` fixture is the existing app test client from `backend/tests/conftest.py`.)

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_homeassistant.py::test_ha_settings_roundtrip_masks_token
```
Expected: FAIL with 404 (route not defined).

- [ ] **Step 3: Add the schema**

In `backend/app/schemas.py`, add near the other settings configs (e.g. after `Go2rtcConfig`):
```python
class HomeAssistantConfig(BaseModel):
    base_url: str
    token: str | None = None  # write-only; omitted on read
```

- [ ] **Step 4: Add the endpoints**

In `backend/app/routers/settings.py`, add `HomeAssistantConfig` to the `from app.schemas import (...)` block, and append this section at the end of the file:
```python
# --- Home Assistant ---


def _upsert_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


@router.get("/homeassistant")
def get_ha_settings(db: Session = Depends(get_db)):
    url_row = db.query(Setting).filter(Setting.key == "ha_base_url").first()
    tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
    base_url = url_row.value if url_row else ""
    connected = bool(base_url and tok_row and tok_row.value)
    return {"base_url": base_url, "connected": connected}


@router.put("/homeassistant")
def update_ha_settings(data: HomeAssistantConfig, db: Session = Depends(get_db)):
    url = data.base_url.rstrip("/")
    _upsert_setting(db, "ha_base_url", url)
    if data.token:  # only overwrite token when a new one is supplied
        _upsert_setting(db, "ha_token", encrypt(data.token))
    db.commit()
    tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
    return {"base_url": url, "connected": bool(tok_row and tok_row.value)}


@router.post("/homeassistant/test")
async def test_ha_connection(data: HomeAssistantConfig, db: Session = Depends(get_db)):
    from app.services.homeassistant import test_connection
    token = data.token
    if not token:  # fall back to the stored token
        tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
        token = decrypt(tok_row.value) if tok_row and tok_row.value else ""
    return await test_connection(data.base_url.rstrip("/"), token)


@router.get("/homeassistant/entities")
async def get_ha_entities(db: Session = Depends(get_db)):
    from app.services.homeassistant import get_ha_config, list_sensor_entities
    cfg = get_ha_config(db)
    if not cfg:
        raise HTTPException(400, "Home Assistant not configured")
    return await list_sensor_entities(*cfg)
```
Add `from app.config import decrypt, encrypt` at the top if not present (the file already imports `encrypt`; add `decrypt`).

- [ ] **Step 5: Run to verify pass**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_homeassistant.py
```
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**
```bash
git add backend/app/schemas.py backend/app/routers/settings.py backend/tests/test_homeassistant.py
git commit -m "feat: Home Assistant settings endpoints"
```

---

### Task 4: Capture-time sensor snapshot

**Files:**
- Modify: `backend/app/services/capture.py`

(The mergeable logic — `build_sensor_snapshot` — is already unit-tested in Task 2. This task wires it into capture with no new test, since `capture_frame` performs real ffmpeg/RTSP work that isn't unit-testable. Verified end-to-end in Task 15.)

- [ ] **Step 1: Add the snapshot block**

In `backend/app/services/capture.py`, find the weather block that ends with `weather_temp, weather_code, weather_is_day = result` (around line 361). Immediately after that block (before the `# Create DB record` comment), insert:
```python
        # Fetch Home Assistant sensor data if configured for this profile
        sensor_data = None
        if profile.ha_sensors:
            import json as _json
            from app.services.homeassistant import (
                build_sensor_snapshot,
                get_ha_config,
                read_sensors,
            )
            cfg = get_ha_config(db)
            if cfg:
                try:
                    entity_ids = [s["entity_id"] for s in _json.loads(profile.ha_sensors)]
                except (_json.JSONDecodeError, TypeError, KeyError):
                    entity_ids = []
                if entity_ids:
                    readings = await read_sensors(cfg[0], cfg[1], entity_ids)
                    sensor_data = build_sensor_snapshot(profile.ha_sensors, readings)
```

- [ ] **Step 2: Store it on the Capture row**

In the `capture = Capture(...)` constructor call, add after `weather_is_day=weather_is_day,`:
```python
            sensor_data=sensor_data,
```

- [ ] **Step 3: Verify the module imports cleanly**

Run:
```bash
cd backend && source .venv/bin/activate && HOME=/tmp python -c "import app.services.capture; print('OK')"
```
Expected: prints `OK`.

- [ ] **Step 4: Commit**
```bash
git add backend/app/services/capture.py
git commit -m "feat: snapshot HA sensor values per captured frame"
```

---

### Task 5: Curated sensor icons

**Files:**
- Create: `backend/scripts/fetch_sensor_icons.sh`
- Create: `backend/app/assets/sensor_icons/*.png` (via the script)
- Create: `backend/app/services/sensor_icons.py`
- Test: `backend/tests/test_sensor_icons.py`

- [ ] **Step 1: Write the fetch script**

`backend/scripts/fetch_sensor_icons.sh`:
```bash
#!/usr/bin/env bash
# Downloads curated multicolor sensor icons (Twemoji, CC-BY 4.0) into
# app/assets/sensor_icons/. Mirrors backend/scripts/fetch_weather_icons.sh.
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/app/assets/sensor_icons"
mkdir -p "$DEST"
BASE="https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72"

declare -A ICONS=(
  [thermometer]=1f321
  [humidity]=1f4a7
  [water]=1f6b0
  [wind]=1f4a8
  [power]=26a1
  [light]=1f4a1
  [battery]=1f50b
  [gauge]=23f1
)

for key in "${!ICONS[@]}"; do
  curl -fsSL "$BASE/${ICONS[$key]}.png" -o "$DEST/$key.png"
  echo "fetched $key"
done
echo "Done. $(ls -1 "$DEST" | wc -l) icons in $DEST"
```

- [ ] **Step 2: Run the script to download icons**

Run:
```bash
chmod +x backend/scripts/fetch_sensor_icons.sh && backend/scripts/fetch_sensor_icons.sh
```
Expected: 8 lines `fetched ...` and `Done. 8 icons ...`. Verify with `ls backend/app/assets/sensor_icons/` → 8 `.png` files.

- [ ] **Step 3: Write the failing test**

`backend/tests/test_sensor_icons.py`:
```python
from app.services import sensor_icons


def test_available_icons_present_on_disk():
    keys = sensor_icons.available_icons()
    assert "thermometer" in keys and "humidity" in keys
    for key in keys:
        assert sensor_icons.icon_path_for(key) is not None, f"missing PNG for {key}"


def test_unknown_or_blank_icon_returns_none():
    assert sensor_icons.icon_path_for("nope") is None
    assert sensor_icons.icon_path_for("") is None
    assert sensor_icons.icon_path_for(None) is None
```

- [ ] **Step 4: Run to verify failure**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_sensor_icons.py
```
Expected: FAIL — `No module named 'app.services.sensor_icons'`.

- [ ] **Step 5: Write the implementation**

`backend/app/services/sensor_icons.py`:
```python
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
```

- [ ] **Step 6: Run to verify pass**

Same command as Step 4. Expected: PASS (2 tests).

- [ ] **Step 7: Commit**
```bash
git add backend/scripts/fetch_sensor_icons.sh backend/app/assets/sensor_icons \
        backend/app/services/sensor_icons.py backend/tests/test_sensor_icons.py
git commit -m "feat: curated sensor icon set + lookup"
```

---

### Task 6: Extract shared frosted-glass primitive

**Files:**
- Create: `backend/app/services/overlay_glass.py`
- Modify: `backend/app/services/weather_overlay.py`

**Goal:** Move the blur→tint→rounded-mask→border code out of `weather_overlay._render_modern` into a shared helper, with weather behavior unchanged.

- [ ] **Step 1: Create the shared helper**

`backend/app/services/overlay_glass.py`:
```python
"""Shared frosted-glass card primitive used by frame overlays."""

from PIL import Image, ImageDraw, ImageFilter

RADIUS = 16


def draw_glass_card(base: Image.Image, x: int, y: int, cw: int, ch: int,
                    radius: int = RADIUS) -> Image.Image:
    """Paste a frosted-glass rounded card onto `base` (an RGBA image) at (x, y)
    with size (cw, ch), then add a translucent highlight border.

    Returns the image to continue drawing on. The border is drawn on its own
    RGBA layer and alpha-composited — drawing it directly then converting to RGB
    would drop the alpha and render a harsh solid-white outline.
    """
    region = base.crop((x, y, x + cw, y + ch)).filter(ImageFilter.GaussianBlur(8))
    tint = Image.new("RGBA", (cw, ch), (20, 22, 28, 150))
    card = Image.alpha_composite(region, tint)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius, fill=255)
    base.paste(card, (x, y), mask)

    border = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [x, y, x + cw - 1, y + ch - 1], radius=radius,
        outline=(255, 255, 255, 70), width=1,
    )
    return Image.alpha_composite(base, border)
```

- [ ] **Step 2: Use it in weather_overlay**

In `backend/app/services/weather_overlay.py`, add the import near the top:
```python
from app.services.overlay_glass import draw_glass_card
```
Then in `_render_modern`, replace the block from `base = img.convert("RGBA")` through the line `base = Image.alpha_composite(base, border)` (the frosted-glass + border code, currently lines ~158-176) with:
```python
    base = img.convert("RGBA")
    base = draw_glass_card(base, x, y, cw, ch, radius=RADIUS)
```
Leave everything else in `_render_modern` (icon, text, `img.paste(base.convert("RGB"))`) unchanged. The now-unused `ImageFilter` import may remain or be removed; if `RADIUS` is still referenced elsewhere keep it.

- [ ] **Step 3: Run the existing weather overlay tests to confirm no regression**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_weather_overlay.py
```
Expected: PASS (same count as before the change).

- [ ] **Step 4: Commit**
```bash
git add backend/app/services/overlay_glass.py backend/app/services/weather_overlay.py
git commit -m "refactor: extract shared frosted-glass card primitive"
```

---

### Task 7: Sensor overlay renderer

**Files:**
- Create: `backend/app/services/sensor_overlay.py`
- Test: `backend/tests/test_sensor_overlay.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_sensor_overlay.py`:
```python
import json
from types import SimpleNamespace

from PIL import Image

from app.services import sensor_overlay


def _cap(data: dict | None):
    return SimpleNamespace(sensor_data=json.dumps(data) if data is not None else None)


def test_compute_layout_none_when_no_data():
    assert sensor_overlay.compute_layout([_cap(None), _cap({})]) is None


def test_compute_layout_locks_width_across_varying_values():
    caps = [
        _cap({"sensor.t": {"value": "1", "unit": "°C", "label": "Temp", "icon": "thermometer"}}),
        _cap({"sensor.t": {"value": "888888", "unit": "°C", "label": "Temp", "icon": "thermometer"}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    assert layout is not None
    assert layout["order"] == ["sensor.t"]
    # Width must accommodate the widest value seen across all frames.
    assert layout["card_w"] > 0 and layout["card_h"] > 0


def test_compute_layout_unions_sensors_first_seen_order():
    caps = [
        _cap({"sensor.a": {"value": "1", "unit": "", "label": "A", "icon": ""}}),
        _cap({"sensor.b": {"value": "2", "unit": "", "label": "B", "icon": ""}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    assert layout["order"] == ["sensor.a", "sensor.b"]


def test_render_frame_runs_and_keeps_size():
    caps = [_cap({"sensor.t": {"value": "21.4", "unit": "°C", "label": "Greenhouse", "icon": "thermometer"}})]
    layout = sensor_overlay.compute_layout(caps)
    img = Image.new("RGB", (640, 360), (40, 80, 120))
    sensor_overlay.render_frame(img, caps[0], "top-left", layout)
    assert img.size == (640, 360)


def test_render_frame_handles_missing_value_row():
    # Layout has two sensors; this frame only has one — the other renders "—".
    caps = [
        _cap({"sensor.a": {"value": "1", "unit": "", "label": "A", "icon": ""},
              "sensor.b": {"value": "2", "unit": "", "label": "B", "icon": ""}}),
        _cap({"sensor.a": {"value": "9", "unit": "", "label": "A", "icon": ""}}),
    ]
    layout = sensor_overlay.compute_layout(caps)
    img = Image.new("RGB", (640, 360))
    sensor_overlay.render_frame(img, caps[1], "bottom-right", layout)  # must not raise
    assert img.size == (640, 360)


def test_render_frame_noop_when_layout_none():
    img = Image.new("RGB", (100, 100))
    sensor_overlay.render_frame(img, _cap(None), "top-left", None)  # must not raise
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_sensor_overlay.py
```
Expected: FAIL — `No module named 'app.services.sensor_overlay'`.

- [ ] **Step 3: Write the implementation**

`backend/app/services/sensor_overlay.py`:
```python
"""Home Assistant sensor overlays baked onto timelapse frames.

A single panel geometry is computed once per render (compute_layout) so the
overlay never resizes/jumps between frames as values change. Layout is derived
from the sensor data actually recorded in the captures, not live profile config.
"""

import functools
import json
import logging

from PIL import Image, ImageDraw, ImageFont

from app.services.overlay_glass import draw_glass_card
from app.services.sensor_icons import icon_path_for

logger = logging.getLogger(__name__)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAD_H = 14      # horizontal padding inside the card
PAD_V = 10      # vertical padding inside the card
ICON_GAP = 7    # gap between icon and label
GAP = 12        # min gap between label column and value column
ROW_GAP = 6     # vertical gap between rows
MARGIN = 16     # distance from the frame edge


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _text_w(draw, text, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(font) -> int:
    try:
        a, d = font.getmetrics()
        return a + d
    except Exception:
        return 12


@functools.lru_cache(maxsize=64)
def _icon(key, size):
    path = icon_path_for(key)
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        logger.warning("Failed to load sensor icon %s", path)
        return None


def _parse(cap) -> dict:
    raw = getattr(cap, "sensor_data", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _value_text(entry: dict) -> str:
    if not entry or entry.get("value") is None:
        return "—"
    return f"{entry.get('value')}{entry.get('unit') or ''}"


def compute_layout(captures, font_size: int = 24) -> dict | None:
    """Compute one fixed panel geometry from the union of sensors recorded in
    `captures`. Returns a dict for render_frame, or None when no sensor data."""
    label_font = _font(max(11, int(font_size * 0.6)))
    value_font = _font(int(font_size * 0.7))
    icon_size = int(font_size * 0.8)

    order: list[str] = []
    meta: dict[str, dict] = {}
    for cap in captures:
        for eid, entry in _parse(cap).items():
            if eid not in meta:
                order.append(eid)
                meta[eid] = {"label": entry.get("label") or eid, "icon": entry.get("icon") or ""}
    if not order:
        return None

    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_label_w = max(_text_w(measure, meta[eid]["label"], label_font) for eid in order)
    max_value_w = 0
    for cap in captures:
        data = _parse(cap)
        for eid in order:
            max_value_w = max(max_value_w, _text_w(measure, _value_text(data.get(eid)), value_font))

    row_h = max(icon_size, _text_h(label_font), _text_h(value_font))
    n = len(order)
    card_w = PAD_H + icon_size + ICON_GAP + max_label_w + GAP + max_value_w + PAD_H
    card_h = PAD_V + n * row_h + (n - 1) * ROW_GAP + PAD_V
    return {
        "order": order,
        "meta": meta,
        "label_font": label_font,
        "value_font": value_font,
        "icon_size": icon_size,
        "row_h": row_h,
        "card_w": card_w,
        "card_h": card_h,
    }


def _anchor(position, W, H, cw, ch):
    m = MARGIN
    if position == "top-right":
        return W - cw - m, m
    if position == "bottom-left":
        return m, H - ch - m
    if position == "bottom-right":
        return W - cw - m, H - ch - m
    return m, m  # top-left default


def render_frame(img, cap, position, layout) -> None:
    """Draw the sensor overlay onto `img` in-place using the locked `layout`."""
    if layout is None:
        return
    data = _parse(cap)
    order = layout["order"]
    cw, ch = layout["card_w"], layout["card_h"]
    icon_size = layout["icon_size"]
    row_h = layout["row_h"]
    label_font = layout["label_font"]
    value_font = layout["value_font"]
    W, H = img.size
    x, y = _anchor(position, W, H, cw, ch)

    base = img.convert("RGBA")
    base = draw_glass_card(base, x, y, cw, ch)
    draw = ImageDraw.Draw(base)

    ix = x + PAD_H
    label_x = ix + icon_size + ICON_GAP
    value_right = x + cw - PAD_H
    cy = y + PAD_V
    for eid in order:
        entry = data.get(eid, {})
        m = layout["meta"][eid]
        ic = _icon(m["icon"], icon_size)
        if ic is not None:
            base.paste(ic, (ix, cy + (row_h - icon_size) // 2), ic)
        lab_y = cy + (row_h - _text_h(label_font)) // 2
        draw.text((label_x, lab_y), m["label"], font=label_font, fill=(255, 255, 255, 220))
        vtext = _value_text(entry)
        vw = _text_w(draw, vtext, value_font)
        val_y = cy + (row_h - _text_h(value_font)) // 2
        draw.text((value_right - vw, val_y), vtext, font=value_font, fill=(255, 255, 255, 255))
        cy += row_h + ROW_GAP

    img.paste(base.convert("RGB"))
```

- [ ] **Step 4: Run to verify pass**

Same command as Step 2. Expected: PASS (6 tests).

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/sensor_overlay.py backend/tests/test_sensor_overlay.py
git commit -m "feat: Home Assistant sensor overlay renderer"
```

---

### Task 8: Render sensor overlay during generation

**Files:**
- Modify: `backend/app/services/timelapse.py`

- [ ] **Step 1: Add the function parameters**

In `generate_timelapse(...)` (line ~334), add after `weather_style: str = "glass",`:
```python
    ha_overlay: bool = False,
    ha_overlay_position: str = "top-left",
```

- [ ] **Step 2: Add the progress step**

After the weather step append (`if weather_overlay: steps.append(... "weather_overlay" ...)`, line ~402-403), add:
```python
        if ha_overlay:
            steps.append({"name": "sensor_overlay", "label": "Applying sensor overlay"})
```

- [ ] **Step 3: Add the render block**

Immediately after the weather overlay render block ends (`await _progress("weather_overlay", "completed")`, line ~535), insert:
```python
        # Step: Home Assistant sensor overlay
        if ha_overlay:
            _check_cancel()
            await _progress("sensor_overlay", "in_progress")
            from PIL import Image
            from app.services.sensor_overlay import (
                compute_layout as sensor_compute_layout,
                render_frame as sensor_render_frame,
            )

            sensor_caps = [c for c in frame_captures if getattr(c, "sensor_data", None)]
            sensor_layout = sensor_compute_layout(sensor_caps) if sensor_caps else None

            if sensor_layout is not None:
                for i, path in enumerate(frame_paths):
                    if cancel_event and i % 10 == 0:
                        _check_cancel()
                    cap = frame_captures[i]
                    if not getattr(cap, "sensor_data", None):
                        continue
                    try:
                        img = Image.open(path)
                        sensor_render_frame(img, cap, ha_overlay_position, sensor_layout)
                        img.save(path, "JPEG", quality=95)
                        img.close()
                    except Exception:
                        logger.warning("Failed to apply sensor overlay to frame %d", i)
            await _progress("sensor_overlay", "completed")
```

- [ ] **Step 4: Verify import + signature**

Run:
```bash
cd backend && source .venv/bin/activate && HOME=/tmp python -c "import inspect, app.services.timelapse as t; assert 'ha_overlay' in inspect.signature(t.generate_timelapse).parameters; print('OK')"
```
Expected: prints `OK`.

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/timelapse.py
git commit -m "feat: render HA sensor overlay during timelapse generation"
```

---

### Task 9: Thread fields through schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add fields to the timelapse/schedule/capture/profile schemas**

In `backend/app/schemas.py` make these additions (mirroring the adjacent `weather_*` lines):

`TimelapseGenerate` — after `weather_style: str = "glass"`:
```python
    ha_overlay: bool = False
    ha_overlay_position: str = "top-left"
```

`TimelapseScheduleCreate` — after its `weather_style: str = "glass"`:
```python
    ha_overlay: bool = False
    ha_overlay_position: str = "top-left"
```

`TimelapseScheduleUpdate` — after its `weather_style: str | None = None`:
```python
    ha_overlay: bool | None = None
    ha_overlay_position: str | None = None
```

`TimelapseScheduleRead` — after its `weather_style: str`:
```python
    ha_overlay: bool
    ha_overlay_position: str
```

`CaptureRead` — after `weather_is_day: bool | None = None`:
```python
    sensor_data: str | None = None
```

`ProfileCreate` — after `weather_enabled: bool = False`:
```python
    ha_sensors: str | None = None  # JSON string: [{entity_id,label,unit,icon}]
```

`ProfileUpdate` — after `weather_enabled: bool | None = None`:
```python
    ha_sensors: str | None = None
```

`ProfileRead` — after `weather_enabled: bool`:
```python
    ha_sensors: str | None = None
```

(`ha_sensors` is intentionally a raw JSON **string**: the model column is `Text`, the profiles router stores it via `**body.model_dump()` with no special-casing, and `build_sensor_snapshot` / `sensor_overlay` parse it defensively. The frontend serializes/deserializes the structure.)

- [ ] **Step 2: Verify schemas import**

Run:
```bash
cd backend && source .venv/bin/activate && HOME=/tmp python -c "import app.schemas; print('OK')"
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**
```bash
git add backend/app/schemas.py
git commit -m "feat: thread ha_overlay/ha_sensors/sensor_data through schemas"
```

---

### Task 10: Thread fields through routers, scheduler, queue

**Files:**
- Modify: `backend/app/routers/timelapse_schedules.py`
- Modify: `backend/app/routers/timelapses.py`
- Modify: `backend/app/services/scheduler.py`
- Test: `backend/tests/test_ha_overlay_schedules.py`

- [ ] **Step 1: Write the failing persistence test**

`backend/tests/test_ha_overlay_schedules.py`:
```python
from unittest.mock import patch


def _create_stream(client):
    return client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]


def _create_profile(client, stream_id):
    with patch("app.routers.profiles.scheduler"):
        return client.post(f"/api/streams/{stream_id}/profiles", json={"name": "P1"}).json()["id"]


def test_schedule_persists_ha_overlay_fields(client):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post("/api/timelapse-schedules/", json={
            "profile_id": pid,
            "name": "nightly",
            "cron_expression": "0 0 * * *",
            "ha_overlay": True,
            "ha_overlay_position": "bottom-left",
        })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ha_overlay"] is True
    assert data["ha_overlay_position"] == "bottom-left"


def test_profile_roundtrips_ha_sensors_json(client):
    sid = _create_stream(client)
    with patch("app.routers.profiles.scheduler"):
        resp = client.post(f"/api/streams/{sid}/profiles", json={
            "name": "GH",
            "ha_sensors": '[{"entity_id":"sensor.t","label":"Temp","unit":"°C","icon":"thermometer"}]',
        })
    assert resp.status_code == 201, resp.text
    assert "sensor.t" in resp.json()["ha_sensors"]
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q tests/test_ha_overlay_schedules.py
```
Expected: FAIL — `KeyError: 'ha_overlay'` (schedule create doesn't persist it yet).

- [ ] **Step 3: Thread through `timelapse_schedules.py`**

In `create_schedule`, in the `TimelapseSchedule(...)` constructor, after `weather_style=body.weather_style,`:
```python
        ha_overlay=body.ha_overlay,
        ha_overlay_position=body.ha_overlay_position,
```

In `trigger_schedule`, in the `enqueue_generation(...)` call, after `weather_style=schedule.weather_style,`:
```python
        ha_overlay=schedule.ha_overlay,
        ha_overlay_position=schedule.ha_overlay_position,
```

- [ ] **Step 4: Thread through `timelapses.py` generate endpoint**

In `backend/app/routers/timelapses.py`, find the `enqueue_generation(...)` call in the generate endpoint and add, after the `weather_style=...` argument (mirror exactly how the weather fields are passed from the request body):
```python
        ha_overlay=body.ha_overlay,
        ha_overlay_position=body.ha_overlay_position,
```
(If that file reads from a differently-named variable than `body`, match the local name used for the other `weather_*` args.)

- [ ] **Step 5: Thread through `scheduler.py`**

In `backend/app/services/scheduler.py`, find `add_timelapse_schedule_job` (where it builds the kwargs/args passed to generation from a `schedule` object — search for `weather_style`). Add alongside the weather fields:
```python
        ha_overlay=schedule.ha_overlay,
        ha_overlay_position=schedule.ha_overlay_position,
```
(Match the exact call style used there — keyword args into `enqueue_generation`/the job function, mirroring `weather_style`.)

- [ ] **Step 6: Verify queue passthrough (no edit expected)**

`generation_queue.enqueue_generation(**kwargs)` and `_worker` (`generate_timelapse(**job_kwargs)`) pass arguments through generically — confirm by reading `backend/app/services/generation_queue.py:41` and `:173-210`. No change needed. If either hard-codes an allowlist of keys, add `ha_overlay` and `ha_overlay_position` there.

- [ ] **Step 7: Run to verify pass**

Same command as Step 2. Expected: PASS (2 tests).

- [ ] **Step 8: Run the full backend suite to confirm no regressions**

Run:
```bash
cd backend && source .venv/bin/activate && rm -f /tmp/lapsora_test.db && \
  LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" HOME=/tmp \
  python -m pytest -p no:cacheprovider -q
```
Expected: all tests PASS (existing + new).

- [ ] **Step 9: Commit**
```bash
git add backend/app/routers/timelapse_schedules.py backend/app/routers/timelapses.py \
        backend/app/services/scheduler.py backend/tests/test_ha_overlay_schedules.py
git commit -m "feat: thread HA overlay fields through routers + scheduler"
```

---

### Task 11: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add types**

In `frontend/src/lib/types.ts`:
- Add `ha_overlay?: boolean` and `ha_overlay_position?: string` to the timelapse-generate options type and the schedule type (wherever `weather_style` appears — mirror it).
- Add `ha_sensors?: string | null` to the Profile type(s) (where `weather_enabled` appears).
- Add `sensor_data?: string | null` to the Capture type (where `weather_is_day` appears).
- Add new interfaces:
```typescript
export interface HomeAssistantConfig {
	base_url: string;
	connected?: boolean;
}

export interface HAEntity {
	entity_id: string;
	friendly_name: string;
	unit: string;
	device_class: string;
}

export interface HASensor {
	entity_id: string;
	label: string;
	unit: string;
	icon: string;
}
```

- [ ] **Step 2: Add API methods**

In `frontend/src/lib/api.ts`, in the returned `api` object near the other `// Settings — go2rtc` methods, add:
```typescript
	// Settings — Home Assistant
	getHAConfig: () => request<HomeAssistantConfig>('/settings/homeassistant'),
	updateHAConfig: (data: { base_url: string; token?: string }) =>
		request<HomeAssistantConfig>('/settings/homeassistant', { method: 'PUT', body: JSON.stringify(data) }),
	testHAConnection: (data: { base_url: string; token?: string }) =>
		request<{ success: boolean; message: string }>('/settings/homeassistant/test', { method: 'POST', body: JSON.stringify(data) }),
	getHAEntities: () => request<HAEntity[]>('/settings/homeassistant/entities'),
```
Add `HomeAssistantConfig`, `HAEntity` to the `import type { ... } from './types'` line at the top of `api.ts`.

- [ ] **Step 3: Verify frontend builds**

Run:
```bash
cd frontend && npm run check
```
Expected: no new type errors referencing the added symbols. (If `npm run check` isn't defined, use `npx svelte-check --tsconfig ./tsconfig.json`.)

- [ ] **Step 4: Commit**
```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types + API for HA integration"
```

---

### Task 12: Settings page — tabs + Integrations

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

**Goal:** Add a tab bar with **General** and **Integrations**. Move the existing go2rtc `<section>` into Integrations and add a Home Assistant card above it.

- [ ] **Step 1: Add tab state**

In the `<script>` block, add:
```typescript
	let activeTab = $state<'general' | 'integrations'>('general');
	let haConfig = $state<HomeAssistantConfig>({ base_url: '', connected: false });
	let haToken = $state('');
	let savingHA = $state(false);
	let testingHA = $state(false);
	let haTestResult = $state<string | null>(null);
```
Add `HomeAssistantConfig` to the `import type { ... }` line. In the existing `$effect(() => { Promise.all([...]) })`, add `api.getHAConfig()` to the array and assign its result to `haConfig` in the `.then(...)` destructuring.

Add the handlers (near `saveGo2rtc`):
```typescript
	async function saveHA() {
		savingHA = true;
		haTestResult = null;
		try {
			const payload: { base_url: string; token?: string } = { base_url: haConfig.base_url };
			if (haToken) payload.token = haToken;
			haConfig = await api.updateHAConfig(payload);
			haToken = '';
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save Home Assistant config');
		} finally {
			savingHA = false;
		}
	}

	async function testHA() {
		testingHA = true;
		haTestResult = null;
		try {
			const payload: { base_url: string; token?: string } = { base_url: haConfig.base_url };
			if (haToken) payload.token = haToken;
			const result = await api.testHAConnection(payload);
			haTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
		} catch (err) {
			haTestResult = err instanceof Error ? err.message : 'Test failed';
		}
		testingHA = false;
	}
```

- [ ] **Step 2: Add the tab bar markup**

In the template, right after `<h1 ...>Settings</h1>` and before the `{#if loading}` block, add:
```svelte
	<div class="flex gap-2 border-b border-gray-800">
		<button
			onclick={() => (activeTab = 'general')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'general' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>General</button>
		<button
			onclick={() => (activeTab = 'integrations')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'integrations' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>Integrations</button>
	</div>
```

- [ ] **Step 3: Gate the existing sections behind the General tab**

Wrap the existing General-tab sections (Display, Notification URLs, Event Toggles, Health Monitoring, Location, Jobs — i.e. everything currently rendered **except** the go2rtc section) in:
```svelte
		{#if activeTab === 'general'}
			<!-- existing sections here, MINUS the go2rtc <section> -->
		{/if}
```

- [ ] **Step 4: Add the Integrations tab with HA + relocated go2rtc**

Add, inside the `{:else}` (loaded) block, after the General block:
```svelte
		{#if activeTab === 'integrations'}
			<!-- Home Assistant -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<div class="mb-4 flex items-center gap-3">
					<h2 class="text-xl font-semibold text-white">Home Assistant</h2>
					<span class="rounded-full px-2 py-0.5 text-xs {haConfig.connected ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}">
						{haConfig.connected ? 'Connected' : 'Not configured'}
					</span>
				</div>
				<p class="mb-4 text-sm text-gray-400">Read sensor entities to overlay on timelapses. Create a long-lived access token in your HA profile.</p>

				<div class="mb-4">
					<label for="ha-url" class="mb-1 block text-sm text-gray-400">Base URL</label>
					<input id="ha-url" type="text" bind:value={haConfig.base_url} placeholder="http://homeassistant.local:8123"
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>
				<div class="mb-4">
					<label for="ha-token" class="mb-1 block text-sm text-gray-400">Long-lived access token</label>
					<input id="ha-token" type="password" bind:value={haToken} placeholder={haConfig.connected ? '•••••••• (leave blank to keep)' : 'Paste token'}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>

				{#if haTestResult}
					<p class="mb-3 text-sm {haTestResult.startsWith('Connected') ? 'text-green-400' : 'text-red-400'}">{haTestResult}</p>
				{/if}

				<div class="flex gap-2">
					<button onclick={testHA} disabled={testingHA || !haConfig.base_url}
						class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50">
						{testingHA ? 'Testing...' : 'Test Connection'}
					</button>
					<button onclick={saveHA} disabled={savingHA}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50">
						{savingHA ? 'Saving...' : 'Save'}
					</button>
				</div>
			</section>

			<!-- go2rtc (relocated from General) -->
			<!-- MOVE the existing go2rtc <section>...</section> here verbatim -->
		{/if}
```
Physically cut the existing go2rtc `<section>` from the General area and paste it where the comment indicates.

- [ ] **Step 5: Verify build + visual**

Run `cd frontend && npm run check` (expect no new errors). Final visual check happens in Task 15.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat: Settings tabs with Integrations (Home Assistant + go2rtc)"
```

---

### Task 13: Profile form — HA sensors section

**Files:**
- Modify: `frontend/src/lib/components/ProfileForm.svelte`

**Goal:** Let a profile pick HA entities; each becomes an editable row (label, unit, icon). Persisted as the `ha_sensors` JSON string on the profile.

- [ ] **Step 1: Add state + load helpers**

In the `<script>` of `ProfileForm.svelte`, add (adapt names to the file's existing form-state conventions; find where `weather_enabled` is bound):
```typescript
	import type { HAEntity, HASensor } from '$lib/types';
	const ICON_KEYS = ['', 'thermometer', 'humidity', 'water', 'wind', 'power', 'light', 'battery', 'gauge'];

	let haSensors = $state<HASensor[]>([]);
	let haEntities = $state<HAEntity[]>([]);
	let haEntitiesLoaded = $state(false);
	let pickEntityId = $state('');

	async function loadHAEntities() {
		try {
			haEntities = await api.getHAEntities();
		} catch {
			haEntities = [];
		}
		haEntitiesLoaded = true;
	}

	function addHASensor() {
		const e = haEntities.find((x) => x.entity_id === pickEntityId);
		if (!e || haSensors.some((s) => s.entity_id === e.entity_id)) return;
		haSensors = [...haSensors, { entity_id: e.entity_id, label: e.friendly_name, unit: e.unit, icon: '' }];
		pickEntityId = '';
	}

	function removeHASensor(id: string) {
		haSensors = haSensors.filter((s) => s.entity_id !== id);
	}
```
- When editing an existing profile, initialize `haSensors` from the loaded profile: `haSensors = profile.ha_sensors ? JSON.parse(profile.ha_sensors) : [];` (place this where the form initializes other fields from the profile being edited).
- In the submit/save handler, include in the payload sent to `api.createProfile`/`updateProfile`: `ha_sensors: haSensors.length ? JSON.stringify(haSensors) : null`.

- [ ] **Step 2: Add the section markup**

Add a section in the form (near the weather toggle), styled to match the form's existing fields:
```svelte
<div class="space-y-2">
	<div class="flex items-center justify-between">
		<label class="text-sm font-medium text-gray-200">Home Assistant Sensors</label>
		{#if !haEntitiesLoaded}
			<button type="button" onclick={loadHAEntities} class="text-xs text-blue-400 hover:underline">Load entities</button>
		{/if}
	</div>

	{#if haEntitiesLoaded}
		<div class="flex gap-2">
			<select bind:value={pickEntityId} class="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200">
				<option value="">Select a sensor…</option>
				{#each haEntities as e}
					<option value={e.entity_id}>{e.friendly_name} ({e.entity_id})</option>
				{/each}
			</select>
			<button type="button" onclick={addHASensor} disabled={!pickEntityId} class="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Add</button>
		</div>
		{#if haEntities.length === 0}
			<p class="text-xs text-gray-500">No sensors found — check the Home Assistant connection in Settings → Integrations.</p>
		{/if}
	{/if}

	{#each haSensors as s (s.entity_id)}
		<div class="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-800/50 p-2">
			<input bind:value={s.label} placeholder="Label" class="w-32 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200" />
			<input bind:value={s.unit} placeholder="Unit" class="w-16 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200" />
			<select bind:value={s.icon} class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200">
				{#each ICON_KEYS as k}
					<option value={k}>{k || 'no icon'}</option>
				{/each}
			</select>
			<span class="flex-1 truncate text-xs text-gray-500">{s.entity_id}</span>
			<button type="button" onclick={() => removeHASensor(s.entity_id)} class="rounded bg-red-900 px-2 py-1 text-xs text-red-300">Remove</button>
		</div>
	{/each}
</div>
```

- [ ] **Step 3: Verify build**

Run `cd frontend && npm run check`. Expected: no new type errors.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/lib/components/ProfileForm.svelte
git commit -m "feat: per-profile Home Assistant sensor picker"
```

---

### Task 14: Generate + Schedule overlay controls

**Files:**
- Modify: `frontend/src/lib/components/GenerateDialog.svelte`
- Modify: `frontend/src/lib/components/ScheduleManager.svelte`

**Goal:** Add an "HA sensor overlay" toggle + position select, mirroring the existing weather overlay controls in each component.

- [ ] **Step 1: GenerateDialog — state**

In `GenerateDialog.svelte`, find the weather overlay form state (search `weather_style` / `weather_position`). Add parallel state:
```typescript
	let haOverlay = $state(false);
	let haOverlayPosition = $state('top-left');
```
In the payload built for `api.generateTimelapse` (where `weather_style`/`weather_position` are included), add:
```typescript
		ha_overlay: haOverlay,
		ha_overlay_position: haOverlayPosition,
```

- [ ] **Step 2: GenerateDialog — markup**

Next to the weather overlay controls, add:
```svelte
<label class="flex items-center gap-2 text-sm text-gray-200">
	<input type="checkbox" bind:checked={haOverlay} class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600" />
	Home Assistant sensor overlay
</label>
{#if haOverlay}
	<select bind:value={haOverlayPosition} class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200">
		<option value="top-left">Top left</option>
		<option value="top-right">Top right</option>
		<option value="bottom-left">Bottom left</option>
		<option value="bottom-right">Bottom right</option>
	</select>
{/if}
```

- [ ] **Step 3: ScheduleManager — state, form reset, edit-populate, save**

In `ScheduleManager.svelte`, mirror exactly how `weather_style`/`weather_position` are handled in all four places:
1. form state object — add `ha_overlay: false, ha_overlay_position: 'top-left'`.
2. `openForm`/reset — set them back to defaults.
3. `openEdit`/populate — `ha_overlay: schedule.ha_overlay ?? false`, `ha_overlay_position: schedule.ha_overlay_position ?? 'top-left'`.
4. save payload (create + update) — include `ha_overlay` and `ha_overlay_position`.

- [ ] **Step 4: ScheduleManager — markup**

Add the same toggle + position `<select>` as Step 2 to the schedule form (bind to the form-state fields rather than standalone `$state`).

- [ ] **Step 5: Verify build**

Run `cd frontend && npm run check`. Expected: no new type errors.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/lib/components/GenerateDialog.svelte frontend/src/lib/components/ScheduleManager.svelte
git commit -m "feat: HA sensor overlay controls in generate + schedule dialogs"
```

---

### Task 15: Docker verification + manual test

**Files:** none (verification only)

- [ ] **Step 1: Rebuild the container (GPU override)**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build
```
Expected: build succeeds, frontend compiles.

- [ ] **Step 2: Start + check logs**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d && \
docker compose -f docker/docker-compose.yml logs --tail=60
```
Expected: migrations `021`/`022`/`023` applied, scheduler starts, no startup errors.

- [ ] **Step 3: Manual UI verification (chrome-devtools MCP)**

Navigate to `http://localhost:8000` and verify:
1. **Settings → Integrations tab** exists; Home Assistant card saves a URL + token (status flips to Connected); "Test Connection" returns a result; go2rtc now lives under Integrations and General no longer shows it.
2. **Profile form**: "Load entities" populates the sensor dropdown (against a real HA, or shows the "no sensors / check connection" hint if none); adding an entity creates an editable row; saving persists (reopen the profile → rows still there).
3. **Generate dialog**: the "Home Assistant sensor overlay" toggle + position select appear.

- [ ] **Step 4: End-to-end overlay check (if a live HA is available)**

With HA configured and a profile that has captured ≥2 frames carrying `sensor_data`, generate a short timelapse with the HA overlay enabled and confirm the vertical sensor panel renders, values change across frames, and the panel does not resize between frames.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```bash
git add -A
git commit -m "fix: HA sensor overlay verification adjustments"
```

(Do not push — leave merge/integration to the finishing-a-development-branch flow.)

## Self-Review

**Spec coverage:**
- Global HA connection (REST + token, encrypted) → Tasks 2, 3.
- Per-profile selection → Tasks 1 (column), 9 (schema), 13 (UI).
- Per-frame JSON snapshot → Tasks 1, 4.
- Vertical glass panel, locked width, recorded-data layout, missing-value `—` → Task 7.
- Curated optional icons → Task 5.
- Shared glass refactor → Task 6.
- Config threading mirroring weather → Tasks 8, 9, 10.
- Integrations tab + go2rtc move → Task 12.
- Generate/schedule controls → Task 14.
- Error handling (HA down → null snapshot, frame kept; render skips dataless frames) → Tasks 2/4/7/8.
- Tests for service/icons/overlay/schedule persistence + migrations → Tasks 2,3,5,7,10.
- Spec's `ha_overlay_style` intentionally dropped (documented at top).

**Type consistency:** `ha_overlay` (bool), `ha_overlay_position` (str), `ha_sensors` (JSON str), `sensor_data` (JSON str), `compute_layout`/`render_frame` signatures, `build_sensor_snapshot`, `icon_path_for`/`available_icons`, `get_ha_config`/`get_states`/`read_sensors`/`list_sensor_entities` — all consistent across tasks.

**Placeholders:** none — every code step contains full content; frontend pattern-mirror steps reference exact files and the concrete adjacent fields to copy.
