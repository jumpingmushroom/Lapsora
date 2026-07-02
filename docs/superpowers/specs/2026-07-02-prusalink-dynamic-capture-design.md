# PrusaLink Dynamic Per-Print Capture — Design

**Date:** 2026-07-02
**Status:** Approved by user (brainstorming session)

## Problem

The PrusaLink integration binds to a single, statically configured capture
profile (`prusalink_config.profile_id`). Every print — a 20-minute benchy or a
14-hour overnight job — uses the same capture interval and render settings.
The three seeded "3D Print - *" templates (Standard / Long / Short) only help
if the user manually re-binds a different profile before each print, which
defeats the point.

PrusaLink's status API already reports per-job metadata (`job.file.name` /
`display_name`, `time_printing`, `time_remaining`) that the poller currently
ignores. The app can know the expected print length at print start.

## Solution overview

Remove profile selection from the integration entirely. PrusaLink binds to a
**camera** (stream). For each print, the poller computes the capture interval
dynamically:

```
target_frames = clip_seconds × clip_fps          (user settings, e.g. 20 s × 25 fps = 500)
interval      = estimated_print_seconds / target_frames
```

clamped to `[min_interval, max_interval]`. Short prints capture densely, long
prints sparsely; every timelapse renders to roughly the configured clip
length. Render uses the existing `fps_mode=target_duration` mechanism so the
clip length self-corrects even when the printer's estimate is off.

Each print becomes a first-class record (`print_jobs`) with the gcode name,
timing, status, and a link to the generated timelapse.

## Data model

### New table: `print_jobs` (migration 029)

| Column | Notes |
|---|---|
| `id` | PK |
| `prusalink_job_id` | job id from PrusaLink status; dedupe guard |
| `gcode_name` | from `job.file.display_name` (fallback `name`) |
| `stream_id` | FK → streams |
| `status` | `printing` / `finished` / `cancelled` |
| `started_at`, `finished_at` | UTC |
| `estimated_seconds` | estimate used for the interval computation (nullable) |
| `interval_seconds` | interval actually applied |
| `timelapse_id` | FK → timelapses, nullable, set after render enqueued/complete |

An open row (`status='printing'`) is the source of truth for an in-flight
print. Replaces the `prusalink_active` / `prusalink_print_started_at`
settings-row hack and survives app restarts.

### Managed profile

The capture and generation pipeline stays profile-based. The integration
auto-creates and owns one profile on the bound camera:

- New column `profiles.managed_by` (nullable text; `'prusalink'` for this one).
- Hidden from the normal profiles UI; the PrusaLink settings section is its
  only editing surface.
- Poller updates its `interval_seconds` per print; render config on it is
  `fps_mode='target_duration'`, `render_target_seconds=clip_seconds`.
- Created (or re-pointed) when the user binds/changes the camera in settings.

### `prusalink_config` blob changes

- `profile_id` → **removed**, replaced by `stream_id`.
- New: `clip_seconds` (default 20), `clip_fps` (default 25),
  `default_interval_seconds` (default 10), `min_interval_seconds` (default 2),
  `max_interval_seconds` (default 120).
- Legacy `fps` / `format` fields and their fallback logic
  (`_profile_render_config` in `prusalink.py`) are removed.
- Unchanged: `poll_interval_seconds`, `generate_on_finish`,
  `generate_on_cancel`, `enabled`.

## Poller behavior

`parse_status` is extended to extract `job.file.display_name` (fallback
`name`), `time_printing`, and `time_remaining` in addition to the current
state/job-id/progress.

**Print start (rising edge to PRINTING):**
1. Create `print_jobs` row (dedupe on `prusalink_job_id`).
2. Estimate = `time_printing + time_remaining` when available. Compute and
   clamp interval; write it to the managed profile; start the capture job.
3. No estimate yet → start at `default_interval_seconds` and recompute
   **once** when the first poll carrying an estimate arrives (update profile
   interval + reschedule the capture job). No further mid-print adjustments.

**Finish:**
1. Stop capture job, mark row `finished`.
2. If `generate_on_finish`: enqueue render for `started_at → now`, named after
   `gcode_name`, with the managed profile's render/overlay options. Store
   `timelapse_id` on the row.

**Cancel / error (state `other` while active):** same stop path, row marked
`cancelled`, render gated on `generate_on_cancel`.

**Restart recovery:** on startup (or first poll), an open `print_jobs` row with
the printer still printing → resume capture; printer idle → close the row via
the normal finish/cancel path.

## Settings UI (Settings → 3D Printing)

- **Connection block:** unchanged (URL, username, password, test).
- **Capture block:** camera select (streams dropdown) replaces the profile
  dropdown; clip length (s); clip fps; default interval (s); min/max interval
  clamp (advanced/collapsed); generate-on-finish and generate-on-cancel
  toggles. The legacy standalone fps/format inputs are removed.
- **Overlays & render block** (collapsible; writes through to the managed
  profile and stored render options):
  - HA sensor overlay — same sensor picker as the normal profile form
  - Logo overlay — toggle
  - Timestamp overlay — toggle, default on (today it is hardcoded `True` in
    the enqueue call; it becomes a real setting)
  - Deflicker — toggle
  - Quality — capture quality slider (default 90)

The enqueue call in `prusalink.py` passes overlay/deflicker/timestamp options
from the managed profile/settings instead of hardcoded values.

## Print history UI

New section on the **timelapses page**: list of `print_jobs` — gcode name,
status, print duration, and thumbnail/link to the generated timelapse.

## Cleanup

- Migration removes the three seeded `is_system` "3D Printing" templates
  (Standard / Long-Overnight / Short-Detail). Profiles created from them keep
  working; `source_template_id` nulls out via existing `ON DELETE SET NULL`.
- Remove `_profile_render_config` legacy fallback and the blob `fps`/`format`
  fields.
- Migrate/remove `prusalink_active` / `prusalink_print_started_at` settings
  rows.

## Out of scope

- Multi-printer support (single global connection kept; schema allows later
  migration).
- Mid-print continuous interval re-adjustment (single recompute only; render
  `target_duration` mode absorbs estimate error).
- Filename-pattern or rule-based profile selection.

## Error handling notes

- Estimate never arrives → whole print runs at `default_interval_seconds`;
  render still normalizes clip length.
- Estimate absurd (0 or negative) → treat as missing.
- Camera unbound or managed profile missing at print start → skip capture,
  emit warning notification (mirrors current early-return behavior).

## Testing

- Unit: interval computation (clamps, missing estimate, recompute-once
  semantics), `decide_transition` unchanged paths, `parse_status` extraction.
- Unit: reconcile lifecycle against a fake PrusaLink status sequence —
  start → estimate arrives → finish; start → cancel; restart mid-print.
- Migration: 029 applies on a copy of an existing DB; seeded templates gone;
  existing bound-profile config converts sanely (old `profile_id` → its
  stream becomes `stream_id`).
- Manual (per CLAUDE.md): rebuild Docker, check logs, drive the settings page
  via Chrome MCP.
