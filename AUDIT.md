# Lapsora Code Review — 2026-06-05

Scope: full `backend/` + `frontend/`, four parallel review passes, cross-checked
against the prior audit (2026-06-02) and verified against current code.

**Bottom line:** the codebase is healthy — several of the prior audit's top items
are already fixed. One serious latent bug remained (capture-gap alerting dead),
plus a cluster of systemic timezone issues and some perf/cleanup wins.

Confidence: **[verified]** confirmed in code/repro · **[likely]** read, not executed
· **[low-conf]** plausible, verify before touching.

---

## 🔴 CRITICAL

### 1. Capture-gap alerting completely dead (TypeError every cycle) [verified]
`backend/app/services/capture_gap.py:52,61` — `datetime.now(UTC)` (aware) minus
`profile.created_at` / `last_capture_at` (SQLite returns naive) raises
`TypeError: can't subtract offset-naive and offset-aware`. The per-profile
`try/except` swallows it, so no gap alert is ever emitted. Reproduced.
**Fix:** normalize to one clock before subtracting; add a regression test.

---

## 🟠 HIGH

### 2. Destructive side-effects before DB commit → inconsistent state [likely]
`routers/profiles.py:88-98` (`delete_profile`), `streams.py:~105-108`
(`delete_stream`). `remove_capture_job` + `shutil.rmtree` run before
`db.delete()/commit()`. Read-only-DB on Unraid is a documented failure mode here,
so a failed commit leaves DB rows pointing at deleted dirs; `restore_jobs` re-adds
jobs on boot. **Fix:** commit first, then remove jobs/files.

### 3. ffmpeg/ffprobe subprocess leaked on timeout [verified]
`services/rtsp.py:75` (`grab_frame`), `:23` (`test_connection`). `wait_for` does
not kill the child on `TimeoutError`. **Fix:** `proc.kill(); await proc.wait()` on
timeout. Same pattern in go2rtc/http_source network awaits.

---

## 🟡 MEDIUM — correctness & performance

### 4. Heatmap index drift misaligns motion overlays [verified]
`services/timelapse.py` `compute_sliding_heatmaps` (~92-144). `append`-based build
shrinks when `cv2.imread` returns None; consumer guard then applies the wrong
frame's heatmap. **Fix:** preallocate `[None]*n`, assign by absolute index.

### 5. Statistics windows skewed on non-UTC hosts [verified]
`routers/statistics.py:58,100,155,188` — `date.today()` (local) vs UTC-stored
`captured_at`. (Prior P1 non-sargable `date(col)` is already fixed.)
**Fix:** derive cutoffs from `datetime.now(UTC).date()`.

### 6. Period-range uses local time vs UTC captures [verified]
`services/timelapse.py:304,397` — `get_period_range` naive local `datetime.now()`
vs UTC captures. Scheduled period timelapses pick the wrong hours off-UTC.

### 7. `get_summary` scans full `captures` table twice [verified]
`routers/statistics.py:25-85` recomputes the full `SUM(file_size)` inside the
`get_storage_stats()` call. **Fix:** reuse precomputed totals.

### 8. Triple decode/re-encode when multiple overlays enabled [verified]
`services/timelapse.py` — weather/sensor/logo are separate per-frame passes, each
decoding+re-encoding every JPEG. **Fix:** composite enabled overlays in one pass.

### 9. Retention orphan scan stats every row each run [likely]
`services/retention.py:69-87` — O(n) DB load + O(n) `os.path.exists` per cleanup.
**Fix:** bounded window / slower cadence; select only `id, file_path`.

### 10. LineChart destroys/rebuilds uPlot on every data change [verified]
`components/LineChart.svelte:20-60` — should `chart.setData()` not `destroy()/new`.

---

## 🟢 LOW — correctness / robustness

- Frontend completion handler deletes an arbitrary generation by index
  `routes/timelapses/+page.svelte:83-93` — key on `data.generation_id` instead.
- Silent `catch {}` blocks hide failures `+layout.svelte:77`, statistics loaders,
  `streams/[id]/+page.svelte:328`, `NotificationBell.svelte:31,40`.
- `MsePlayer.svelte:65` queue grows unbounded on incompatible stream.
- `services/generation_progress.py:46-53` `fail_generation` dead status assignment.
- `services/go2rtc.py:66,81` dead `last_exc` + unreachable `raise`.
- `_icon` lru_cache returns shared mutable PIL images (read-only today)
  `weather_overlay.py:62`, `sensor_overlay.py:48`.
- Settings config load/save N+1 per field `routers/settings.py`.

---

## ⚪ Dead code / hygiene

- `backend/lapsora.egg-info/` committed — `git rm -r --cached` + gitignore.
- `aiofiles` unused dependency `backend/pyproject.toml:16` (keep `python-multipart`
  — now used by the logo-upload endpoint).
- `ProfileForm.svelte` `mode` prop dead.
- `statistics/+page.svelte:163-173` `projectionDays` computes then discards work.
- Duplicated `formatBytes`/`formatDuration` in StorageStats/TimelapsePlayer vs
  `utils.ts` (StorageStats copy drops the null→"--" handling).
- `Timelapse` TS interface missing `thumbnail_path` (runtime fine, type only).
- `types.ts Go2rtcStreamInfo.producers` unused field.

---

## ⏱ Cross-cutting theme: no canonical timezone
#1, #5, #6 (+ prior C1 manual active-hours) share one root: captures stored
UTC-naive while gap/stats/period/active-hours mix aware UTC and naive local time.
Needs a product decision (server-local vs UTC for "active hours") then one shared
helper used everywhere.

---

## ✅ Already fixed since 2026-06-02 (don't re-raise)
- Statistics index (prior P1) — now sargable `captured_at >= :cutoff`.
- Async cancel race (prior C2) — `system.py:50` now `async def`.
- Weather-overlay misalignment (prior C3) — `frame_captures` aligned to `frame_paths`.
- `python-multipart` "unused" (prior D3) — now used by logo upload.
- Path traversal — file paths are server-generated, not user input.
