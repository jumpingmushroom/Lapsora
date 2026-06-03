# Weather Icon Overlay — Design

**Date:** 2026-06-03
**Status:** Approved design, pending implementation plan

## Problem

The weather overlay baked onto finished timelapses is a plain semi-transparent
black box showing `15°C Rain` (rendered per-frame with Pillow in
`backend/app/services/timelapse.py`). It's functional but visually dull. We want
to prettify it with real multicolor weather icons, while letting users keep the
old look if they prefer.

## Goals

- Replace the plain text box with a polished, icon-based weather overlay.
- Offer multiple overlay **styles**, including the current one, as a user choice.
- Use real multicolor weather icons with **day/night** variants.
- Guarantee the overlay does **not** jump/resize between frames as the condition
  changes during a timelapse.

## Non-goals

- Animated icons.
- Monochrome icon option (we ship multicolor only — YAGNI).
- Reworking weather *fetching* beyond adding the day/night flag.
- Changing the existing `weather_position` / `weather_unit` / `weather_font_size`
  controls (they continue to apply to every style).

## Design overview

### 1. The `weather_style` setting

A new enum chooses the overlay look. All styles honor the existing position,
unit, and font-size controls.

| Value     | Description                                            |
|-----------|--------------------------------------------------------|
| `minimal` | The current plain black text box, **unchanged**.       |
| `badge`   | Rounded pill: icon + large temperature only.           |
| `glass`   | **Default.** Frosted card: icon + temp + condition.    |
| `strip`   | Glass card plus secondary line (hi/lo + frame time).   |

**Default is `glass`.** Existing schedules get `glass` via the column default, so
any schedule that already had `weather_overlay` on will produce the nicer card on
its next render. `minimal` reproduces today's output byte-for-similar so anyone
who prefers it can opt back in.

### 2. Day/night capture

Open-Meteo's `current` block can return `is_day` (1/0). We add it to the request
and persist it per capture.

- `backend/app/services/weather.py`
  - Add `is_day` to the `current` params.
  - `get_current_weather` returns `(temp, code, is_day)`; cache tuple extended.
  - Callers in `capture.py` updated to store the new field.
- New nullable column `captures.weather_is_day` (INTEGER, nullable). Captures
  recorded before this change are `NULL` → icon mapping falls back to the **day**
  variant.

### 3. Icon set

- Bundle a **multicolor PNG icon set** under `backend/app/assets/weather_icons/`.
  Source: an MIT-licensed set such as Meteocons (static SVGs rasterized to PNG
  masters offline at ~256px and committed). No runtime SVG rasterization, so **no
  new system dependency** (no cairosvg/Cairo).
- A mapping module resolves `(weather_code, is_day)` → icon filename. Day/night
  variants exist for conditions where it matters (clear, mostly clear, partly
  cloudy); rain/drizzle/snow/fog/thunderstorm reuse a single icon regardless of
  day/night.
- At render time, load the PNG master once and downscale to the target pixel size
  with Pillow `LANCZOS` (icon size derived from `weather_font_size`). Cache scaled
  icons per render to avoid repeated resizing.
- Mapping must cover every `WMO_CODES` key (0,1,2,3,45,48,51–57,61–67,71–77,
  80–86,95,96,99) plus a generic fallback icon for unknown codes.

### 4. Locked-width rendering (no jumping)

Root cause of jump: the box is right-anchored and its width grows with text, so
the left edge shifts when the condition label changes length between frames.

**Fix — single pre-pass before the per-frame loop:**

1. Collect the distinct `(temp string, condition label)` pairs that actually
   appear across this timelapse's `frame_captures`.
2. Measure each with the chosen font; take the maximum text width.
3. Lock the card geometry once (icon box + gap + max text width + padding) for
   the whole render.
4. Render every frame at that fixed geometry, anchored by the chosen corner.
   Labels longer than the locked width (rare) are ellipsized.

This sizes the card to *this* timelapse's real conditions — no wasted space, no
movement. Applies to `badge`, `glass`, `strip`. `minimal` keeps its current
per-frame sizing (acceptable — it's the legacy look).

### 5. Glass rendering in Pillow

The frosted look is produced per-frame (the blur depends on the background behind
the card, which differs each frame):

1. Compute the locked card rectangle at the anchored position.
2. Crop that region from the frame, apply `GaussianBlur` (radius ~8), darken
   slightly, paste back.
3. Draw a rounded-rectangle panel (`ImageDraw.rounded_rectangle`) with a
   semi-transparent dark fill and a subtle 1px white-ish border.
4. Composite the RGBA icon, then draw the temperature and condition text.

`badge` and `strip` reuse the same primitives with different layouts.
**Performance note:** the per-frame crop+blur is heavier than the current single
text box; for very long timelapses this adds encode-prep time. Acceptable; if it
becomes a problem we can optimize later (out of scope).

### 6. API / schema

Add `weather_style: str` to:

- `TimelapseGenerate` (default `"glass"`)
- `TimelapseScheduleCreate` (default `"glass"`)
- `TimelapseScheduleUpdate` (`str | None = None`)
- `TimelapseScheduleResponse` (`str`)

Optionally surface `weather_is_day` on the capture response schema (lines
168–169) if useful to the frontend; not required for the overlay itself.

The `timelapse_generate` / schedule plumbing in `routers/timelapses.py` and the
generation function signature in `timelapse.py` thread `weather_style` through to
the overlay step.

### 7. Database migrations

Two new SQL migrations (auto-applied on startup), following the existing pattern:

- `019_weather_is_day.sql` — `ALTER TABLE captures ADD COLUMN weather_is_day INTEGER;`
- `020_weather_style.sql` — `ALTER TABLE timelapse_schedules ADD COLUMN weather_style TEXT DEFAULT 'glass';`

(Model fields added to `Capture` and `TimelapseSchedule` in `models.py` to match.)

### 8. Frontend

In `GenerateDialog.svelte` and `ScheduleManager.svelte`, add a **Style** dropdown
(Minimal / Badge / Glass / Strip) within the existing weather-overlay controls,
shown when `weather_overlay` is enabled. Add `weather_style` to `types.ts`.
Default selection `glass`.

## Affected files

- `backend/app/services/weather.py` — `is_day` fetch + return shape.
- `backend/app/services/capture.py` — store `weather_is_day`.
- `backend/app/services/weather_icons.py` *(new)* — `(code, is_day)` → icon path + mapping.
- `backend/app/assets/weather_icons/*.png` *(new)* — bundled multicolor masters.
- `backend/app/services/timelapse.py` — locked-width pre-pass + styled rendering.
- `backend/app/models.py` — `Capture.weather_is_day`, `TimelapseSchedule.weather_style`.
- `backend/app/schemas.py` — `weather_style` on the four schemas above.
- `backend/app/routers/timelapses.py` — thread `weather_style` through.
- `backend/app/migrations/versions/019_weather_is_day.sql` *(new)*.
- `backend/app/migrations/versions/020_weather_style.sql` *(new)*.
- `frontend/src/lib/types.ts` — `weather_style` field.
- `frontend/src/lib/components/GenerateDialog.svelte` — style dropdown.
- `frontend/src/lib/components/ScheduleManager.svelte` — style dropdown.

## Verification

Per `CLAUDE.md`: rebuild with the GPU compose override, bring the stack up, check
logs (migrations 019/020 applied cleanly, scheduler starts), then in Chrome MCP
DevTools generate timelapses exercising each style and confirm icons render,
day/night variants resolve, and the box stays fixed as conditions change.

## Open questions

None — design approved in brainstorming (Glass default, multicolor icons,
locked-width, day/night capture, four styles with current renamed "Minimal").
