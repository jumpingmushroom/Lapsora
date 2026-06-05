# IR-only Frame Filter — Design

**Date:** 2026-06-05
**Status:** Approved (pending implementation plan)

## Problem

Profiles can gate captures by sun position (`capture_mode = sun`, e.g. `night`).
But sunset/sunrise is a poor proxy for when a camera's IR illuminator actually
engages. IR turns on when the scene gets dark *enough*, which is typically later
than sunset and earlier than sunrise. The result is a band of color frames
mixed into what should be a clean IR (greyscale) night timelapse.

Goal: capture/keep **only true IR frames** — frames the camera has rendered in
monochrome because its IR-cut filter is open and IR illumination is active.

Out of scope: color-IR cameras (cameras that keep color at night). Not handled.

## Landscape (why this approach)

- The robust, source-agnostic signal is the **image itself**: an IR frame is
  monochrome (R≈G≈B everywhere → near-zero color). This is how the surveillance
  ecosystem handles it. Frigate has the same problem and the community settles
  on image saturation/RGB-spread analysis
  ([Frigate #6851](https://github.com/blakeblackshear/frigate/discussions/6851),
  [#3960](https://github.com/blakeblackshear/frigate/issues/3960)).
- Grayscale detection is cheap and well understood: HSV mean saturation, or mean
  per-pixel chroma `max(R,G,B) − min(R,G,B)`
  ([grayscale-image-detector](https://github.com/datable-be/grayscale-image-detector)).
- ONVIF cameras expose a true IR-cut-filter state via `GetImagingSettings →
  IrCutFilter`
  ([ONVIF Imaging Spec](https://www.onvif.org/onvif/specs/srv/img/ONVIF-Imaging-Service-Spec.pdf)),
  but Lapsora's sources are RTSP/go2rtc/HTTP, not ONVIF. Noted as a future
  per-camera enhancement; not the foundation.

The capture path already decodes frames with PIL + numpy in memory (see
`_is_frame_corrupt()` in `capture.py`), so saturation analysis drops in cleanly.

## Design

### Separation of concerns

The IR check is **post-capture** (you must fetch a frame to measure it), which
is a different decision than `capture_mode` (a *pre-capture* time gate). They
stay separate and compose:

- `capture_mode` (always / manual / sun) → **when do we fetch a frame**
- IR filter (new) → **do we keep this frame**

Usage combinations this enables:
- `sun:night` + IR filter — sun window cheaply avoids pointless daytime fetches;
  the IR filter fixes the dusk/dawn edges where sun timing is wrong.
- `always` + IR filter — pure "only when greyscale", independent of season/location.

### Detection metric

Per-pixel **chroma spread** = `max(R,G,B) − min(R,G,B)`, averaged over the
frame, normalized to a **0–100** scale.

- True IR / greyscale frame → ~0 (all channels equal).
- Daytime color → clearly higher (tens).
- **Keep frame if mean chroma ≤ threshold**, otherwise discard.

Chosen over HSV saturation: it's a one-liner in numpy (already a capture-path
dependency), needs no colorspace conversion, and separates gray vs color
identically. Computed on a **downsampled copy** (~256px wide) so cost is
negligible even at full capture resolution.

### Data model

One migration adding two columns to `profiles`:

- `ir_only` BOOLEAN DEFAULT FALSE — the filter toggle
- `ir_chroma_threshold` REAL DEFAULT 10.0 — tunable cutoff (0–100)

Mirrored into `ProfileCreate` / `ProfileUpdate` / `ProfileRead` schemas.
No scheduler reschedule needed — the filter is post-capture and does not affect
timing, so `ir_only` / `ir_chroma_threshold` are NOT added to the profiles
router's `needs_reschedule` set.

### Detection module

`backend/app/services/ir_detect.py` — one pure, I/O-free function:

```python
def mean_chroma(img: Image.Image) -> float:
    # downsample (~256px wide) → numpy RGB array
    # mean(max over channels - min over channels), normalized to 0..100
```

Isolated and trivially unit-testable.

### Capture hook

In `capture.py`, after the frame is decoded but **before** the final
save / `Capture` DB record is created — alongside the existing
`_is_frame_corrupt()` check, same pattern, same place:

```
if profile.ir_only and mean_chroma(img) > profile.ir_chroma_threshold:
    log.debug("skip non-IR frame: chroma=%.1f > %.1f", chroma, threshold)
    # remove any temp file; return without creating a Capture
    return
```

Rejected frames are **silently discarded** — no file, no DB record. The debug
log line is the only trace, kept so the threshold can be tuned without flying
blind. The corruption check still runs as before.

Note: byte-source captures (`go2rtc`, `http_*`) that currently skip PIL decode
when no resize/quality change is requested must decode the JPEG (from the
in-memory bytes) when `ir_only` is enabled, in order to run the check.

### Data flow

```
scheduler
  → capture_frame
    → fetch bytes / ffmpeg
    → decode (PIL)
    → [corruption check]
    → [IR check]  ← new: discard if mean_chroma > threshold
    → resize / quality
    → save file + Capture record
```

### Test endpoint

`GET /api/streams/{stream_id}/ir-test` — reuses
`providers.grab_preview(stream, db)` to fetch a live frame, runs `mean_chroma()`,
returns:

```json
{ "chroma": 3.2, "preview": "<base64 jpeg>" }
```

Lives in the **streams** router: it operates on a stream and must work even
while a not-yet-created profile is being configured. Returns the thumbnail so
the user can confirm the camera is actually in IR when they sample.

### UI (`ProfileForm.svelte`)

New collapsible "IR-only capture" section:

- Checkbox `ir_only`. When off, the rest is hidden.
- When on: threshold number input (`ir_chroma_threshold`, 0–100) + a
  **"Test now"** button.
- Test shows: the live thumbnail, the measured **chroma value**, and a live
  verdict badge — *"would KEEP (3.2 ≤ 10)"* (green) / *"would SKIP (28.4 > 10)"*
  (red) — recomputed instantly as the threshold changes.
- Tuning workflow: sample once in daylight, once at night, set the threshold
  between the two measured numbers.

## Testing

- **Unit** (`ir_detect`): synthetic numpy frames — solid gray → ~0, saturated
  red → high, gradient → mid. Assert the metric separates them and that the
  keep/discard boundary lands as expected around a chosen threshold.
- **Manual** (per CLAUDE.md): rebuild with the GPU compose override, confirm
  logs are clean and the migration applied, then via Chrome DevTools at
  `localhost:8000` — toggle IR-only on a profile, hit Test, confirm the chroma
  value + verdict render and that dragging the threshold updates the badge.

## Deliberately out of scope (YAGNI)

- **ONVIF `IrCutFilter` query** — a future per-camera enhancement; sources today
  aren't ONVIF.
- **Hysteresis / flap-handling at dusk** — silent discard already handles
  transition frames correctly; no extra machinery needed.
- **Keeping rejected frames / DB flags** — pure discard, confirmed.
- **Color-IR cameras** — explicitly unsupported for now.
