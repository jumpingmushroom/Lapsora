# Sun Events Capture Mode — Design

## Summary

Extend the existing "sun" capture mode with selectable sun events (daylight, golden hour, blue hour, night). Users check which time windows to capture during. Multiple selections are unioned together.

## Sun Events & Time Windows

| Event | Time Window |
|-------|-------------|
| **Daylight** | Sunrise to Sunset |
| **Golden hour** | Sunrise to Sunrise+1h, Sunset-1h to Sunset |
| **Blue hour** | Civil dawn to Sunrise, Sunset to Civil dusk |
| **Night** | Civil dusk to Civil dawn (next day) |

All times computed daily via the `astral` library (already a dependency). The existing `sun_offset_minutes` applies as a uniform buffer to all windows.

When no events are selected (or `sun_events` is empty), defaults to Daylight — preserving backward compatibility with existing "sun" mode profiles.

## Schema

One new column on `profiles`:

```sql
ALTER TABLE profiles ADD COLUMN sun_events TEXT NOT NULL DEFAULT '';
```

Stored as comma-separated values, e.g. `"golden_hour,blue_hour"` or `""` for daylight default.

## Backend Changes

### Model (`backend/app/models.py`)
- Add `sun_events: Mapped[str]` to `Profile`

### Schemas (`backend/app/schemas.py`)
- `ProfileCreate`: `sun_events: str = ""`
- `ProfileUpdate`: `sun_events: str | None = None`
- `ProfileRead`: `sun_events: str`

### Capture service (`backend/app/services/capture.py`)
Refactor `_is_within_active_window()` sun branch:
1. Parse `profile.sun_events` into a set (e.g. `{"golden_hour", "blue_hour"}`)
2. If empty, use `{"daylight"}` as default
3. Compute all relevant time windows using `astral`:
   - `daylight`: sunrise to sunset
   - `golden_hour`: sunrise to sunrise+1h, sunset-1h to sunset
   - `blue_hour`: civil dawn to sunrise, sunset to civil dusk
   - `night`: civil dusk to civil dawn
4. Apply `sun_offset_minutes` buffer
5. Check if current time falls within any window (union)

### No changes needed to:
- Scheduler (captures run on interval, filtering happens at capture time)
- Timelapse generation
- Any other service

## Frontend Changes

### Types (`frontend/src/lib/types.ts`)
- Add `sun_events: string` to `Profile`
- Add `sun_events?: string` to `ProfileCreate` and `ProfileUpdate`

### ProfileForm component
When capture mode is "sun", show checkbox group below offset input:

```
Sun Events:
  [x] Daylight (sunrise to sunset)
  [ ] Golden hour (warm light)
  [ ] Blue hour (twilight)
  [ ] Night (dusk to dawn)

  Select which parts of the day to capture. Multiple selections are combined.
```

- "Daylight" checked by default
- Checkboxes only visible when capture_mode is "sun"
- Stored as comma-separated string in API calls

## Migration

New file: `backend/app/migrations/versions/014_sun_events.sql`

## Backward Compatibility

- Existing "sun" profiles have `sun_events = ""` which defaults to daylight behavior
- No behavior change for existing profiles
- New column has `DEFAULT ''` so no null handling needed
