# Home Assistant Sensor Overlay — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorm), pending implementation plan

## Summary

Add a Home Assistant integration that pulls sensor entity values and overlays
them onto generated timelapses, alongside the existing weather overlay. The
feature mirrors the weather pipeline: global connection config → per-frame
snapshot at capture time → locked-width overlay rendered at generation time.
A new **Integrations** tab in Settings holds the Home Assistant connection (and
absorbs the existing go2rtc config).

## Decisions (from brainstorm)

| Question | Decision |
|----------|----------|
| HA connection mechanism | REST API + long-lived access token (pull), global config |
| Sensor selection scope | Per-profile (each camera picks its own entities) |
| Per-frame storage | JSON column on `captures` (snapshot dict) |
| Overlay layout | Vertical glass panel: one card, label→value rows |
| Icons | Curated bundled multicolor set, optional per sensor |
| Settings structure | Introduce a tab bar; build the **Integrations** tab only |
| go2rtc | Moves into the Integrations tab |

Two defaults chosen during design review:
- Per-profile sensor list stored as a **JSON column on `profiles`**, not a child
  table (matches the "keep it simple, JSON" storage decision).
- Render layout is derived from the **recorded `sensor_data`** in the captures,
  not the live profile config, so old timelapses render true to what was
  captured even if the profile's sensor set later changes.

## Architecture

Three stages, same split as the weather feature:

1. **Global config** — HA base URL + long-lived token stored in the `settings`
   table; token encrypted with the existing `encrypt()`/`decrypt()` helpers.
2. **Capture time** — each frame snapshots the profile's configured sensor
   values into the capture row.
3. **Render time** — overlay drawn from those per-frame snapshots, with a
   single locked-width geometry computed once per render so it never jumps
   between frames as values change.

New backend modules (each parallels an existing weather counterpart):
- `services/homeassistant.py` — REST client (counterpart: `weather.py`)
- `services/sensor_overlay.py` — renderer (counterpart: `weather_overlay.py`)
- `services/sensor_icons.py` + `assets/sensor_icons/*.png` — curated icon set
  (counterpart: `weather_icons.py` + `assets/weather_icons/`)

## Data model (3 migrations)

- **`021_capture_sensor_data.sql`** — `ALTER TABLE captures ADD COLUMN sensor_data TEXT;`
  JSON snapshot, e.g.:
  ```json
  {
    "sensor.gh_temp": {"value": 21.4, "unit": "°C", "label": "Greenhouse", "icon": "thermometer"},
    "sensor.gh_humidity": {"value": 62, "unit": "%", "label": "Humidity", "icon": "humidity"}
  }
  ```
- **`022_profile_ha_sensors.sql`** — `ALTER TABLE profiles ADD COLUMN ha_sensors TEXT;`
  JSON list of configured sensors: `[{entity_id, label, unit, icon}]`. Empty/null = off.
- **`023_schedule_ha_overlay.sql`** — on `timelapse_schedules`:
  `ha_overlay BOOLEAN`, `ha_overlay_style TEXT`, `ha_overlay_position TEXT`.

JSON is stored as TEXT (SQLite) and parsed in the app, consistent with how
other small structured values are handled.

Corresponding SQLAlchemy model changes:
- `Capture.sensor_data: Mapped[str | None]` (Text, nullable)
- `Profile.ha_sensors: Mapped[str | None]` (Text, nullable)
- `TimelapseSchedule.ha_overlay` (Boolean, default False), `ha_overlay_style`
  (Text, default "glass"), `ha_overlay_position` (Text, default "top-left")

## HA service + endpoints

`services/homeassistant.py`:
- `get_states(base_url, token)` → `GET /api/states` with `Authorization: Bearer <token>`.
  Short TTL cache (~15s) keyed by base_url so near-simultaneous profile captures
  don't each hit HA. Returns the full state list.
- `test_connection(base_url, token)` → validates reachability + auth.
- `list_sensor_entities(base_url, token)` → filters to sensor-ish domains,
  returns `entity_id`, `friendly_name`, `unit_of_measurement`, `device_class`
  for the picker.
- `read_sensors(base_url, token, entity_ids)` → builds `{entity_id: {value, unit}}`
  for a profile's configured entities (uses the cached `get_states`).

Settings router additions under `/api/settings/homeassistant`:
- `GET /homeassistant` → `{base_url, connected}` (token never returned)
- `PUT /homeassistant` → save base_url + token (token encrypted)
- `POST /homeassistant/test` → `{success, message}`
- `GET /homeassistant/entities` → list for the picker

Settings keys: `ha_base_url`, `ha_token` (encrypted).

## Capture flow

In `capture.py`, immediately after the existing weather block: if
`profile.ha_sensors` is non-empty **and** HA is configured, fetch states (via
the cached `get_states`), build the snapshot dict for that profile's entities,
and store it in `capture.sensor_data`. On HA error/timeout, log a warning and
leave `sensor_data` null — the frame is still captured (same resilience as
weather).

## Render flow

`services/sensor_overlay.py` (parallels `weather_overlay.py`):
- `compute_layout(captures, style, font_size)` — scans the **union of sensors
  present across the captures' `sensor_data`**, measures the max label width and
  max value width, and returns one locked vertical-panel geometry (card
  width/height, row height, fonts, icon size). Units are taken verbatim from the
  snapshot (HA provides them); no C/F-style conversion as weather does.
- `render_frame(img, cap, layout, style, position)` — draws a frosted-glass
  panel and one row per sensor: icon + label on the left, value on the right.
  A sensor missing from a given frame renders `—` so the row set (and thus the
  layout) stays stable.
- Icons via `sensor_icons.py` with an `lru_cache`d load+resize, exactly like the
  weather `_icon` helper.

**Targeted refactor:** extract the frosted-glass card drawing (blur region →
tint → rounded mask paste → border on its own alpha-composited layer) from
`weather_overlay.py` into a small shared helper that both overlays use, to avoid
duplicating the fiddly alpha code. Keep the weather overlay's behavior identical.

Weather and sensor overlays render independently — both can appear in one
timelapse, with independent positions (sensor default `top-left`, weather
default `bottom-right`).

`timelapse.generate_timelapse(...)` gains `ha_overlay`, `ha_overlay_style`,
`ha_overlay_position` params; computes the sensor layout once (when
`ha_overlay` and any capture has `sensor_data`) and calls `render_frame` per
frame.

## Config threading

`ha_overlay` (bool), `ha_overlay_style`, `ha_overlay_position` added to:
- `TimelapseGenerate`, `TimelapseScheduleCreate`, `TimelapseScheduleUpdate`,
  `TimelapseScheduleRead` (schemas)
- the `TimelapseSchedule` model (columns above)
- `routers/timelapses.py`, `routers/timelapse_schedules.py` (both
  `create_schedule` **and** `trigger_schedule`), `services/scheduler.py`,
  `services/generation_queue.py`, `services/timelapse.py`

This mirrors the existing `weather_*` fields exactly, including the
create_schedule/trigger persistence the recent schedule-bug fix established.

## Frontend

- **Settings (`settings/+page.svelte`)** — introduce a tab bar with **General**
  (existing sections minus go2rtc) and **Integrations** tabs. Integrations holds:
  - **Home Assistant** card: base URL, token (masked), Test connection, Save,
    connection status pill.
  - **go2rtc** card relocated from the flat page.
- **Profile form** — a "Home Assistant Sensors" section: add entities via
  autocomplete from `/homeassistant/entities` (auto-fills label + unit from HA
  on add), each row with editable label/unit and an icon chosen from the curated
  picker. Persists to `profile.ha_sensors`.
- **GenerateDialog + ScheduleManager** — HA overlay toggle + style + position
  selects, mirroring the weather overlay controls (only meaningful when the
  profile has sensors configured).

## Curated icon set

Bundled multicolor PNGs in `backend/app/assets/sensor_icons/`, mapped by a
stable key (e.g. `thermometer`, `humidity`, `water`, `wind`, `power`, `light`,
`co2`, `gauge`). `sensor_icons.py` exposes `icon_path_for(key)` returning an
absolute path or None; a blank icon renders a clean label+value row. The icon
picker in the profile UI lists the available keys.

## Error handling

- HA unreachable/timeout at capture → null snapshot, frame still saved.
- At render, frames without `sensor_data` are skipped; layout is computed from
  frames that have data. If no captures have data, no overlay is drawn.
- Token stored encrypted at rest; never returned by the GET endpoint.
- Entity removed/unavailable in HA → renders `—` for that row.

## Testing

- `services/homeassistant.py` — mocked httpx: `get_states`, `test_connection`,
  `list_sensor_entities`, error/timeout handling, cache behavior.
- `sensor_icons.py` — key→path mapping, missing key returns None.
- `sensor_overlay.py` — `compute_layout` locked width across varying values;
  `render_frame` doesn't crash, handles missing-value rows.
- Schedule round-trips `ha_overlay` / `ha_overlay_style` / `ha_overlay_position`
  (parallels `test_timelapse_schedules.py`).
- Migrations `021`–`023` apply cleanly on startup.

## Out of scope (YAGNI)

- WebSocket/MQTT transports (REST pull only).
- Normalized per-reading table / per-sensor charts or sparklines.
- Auto-importing HA's mdi icons (curated set instead).
- Full reorganization of every Settings section into tabs (only General +
  Integrations now).
