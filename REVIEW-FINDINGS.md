# Code Review — Lapsora — 2026-07-05 — reviewed by Fable 5

Severity scale: **SEV-1** exploitable security / data loss · **SEV-2** user-facing bug or crash · **SEV-3** latent bug / reliability risk · **SEV-4** hygiene worth doing.
(Maps to Critical / High / Medium / Low.)

Calibration: per the project's stated threat model (self-hosted, local-network only), auth/CORS/SSRF were deliberately **not** reviewed as security issues. Review focused on correctness, data integrity, and reliability. Every finding below was traced to source; line numbers refer to the current `main` (835a0e6).

## Summary

The codebase is in good shape overall: subprocess handling is consistently `exec`-style (no shell injection surface), raw SQL is parameterized, the generation queue is correctly single-flight, frontend/backend API contracts match, and SSE/interval/observer cleanup on the frontend is thorough. No SEV-1 findings. The dominant risk cluster is **data integrity around deletion**: a validation gap that lets a cleanup schedule be updated to retain 0 days, an orphan-record sweep that trusts `os.path.exists` on a deployment with a documented recurring permission-flap failure mode, and delete endpoints that unlink media before committing. The second cluster is the **`auto_disabled` flag lifecycle**, where three separate paths can leave the flag stale and cause health recovery to re-enable profiles the user (or the PrusaLink integration) deliberately stopped. The test suite is substantial (183 passing) but has four environment-dependent failures and two tests that touch the real data directory.

## Category coverage

1. **Security** — No SQL injection (statistics f-string fragments are constant strings; all values bound). No secrets committed (`.env` gitignored, `.env.example` has placeholders). Findings limited to credential leakage into logs/notifications (F-16) and a filename-interpolation hygiene issue (F-33). Auth/CORS/SSRF out of scope by owner decision.
2. **Correctness bugs** — findings F-2, F-3, F-4, F-11–F-15, F-19–F-24, F-26–F-31.
3. **Error handling** — findings F-12, F-17, F-18, F-20, F-25, F-36, F-40.
4. **Data integrity** — findings F-1, F-5–F-10.
5. **Dead code** — very little; see F-44. Verified: all 15 Svelte components used, no dead endpoints (every router path referenced from `api.ts`), integration-service helpers all have live callers.
6. **Performance** — findings F-32, F-41, F-42, F-45.
7. **Consistency** — findings F-34, F-43; known drift (in-tree `docs/` vs CLAUDE.md rule) already tracked as pending work, not re-reported.
8. **Test coverage gaps** — findings F-35–F-39.

## Findings

### Data integrity

### [SEV-2] F-1: Cleanup schedule update accepts retention of 0/negative days → mass deletion
- **FIXED:** Added `Field(default=None, ge=1)` to `capture_retention_days`/`timelapse_retention_days` in `CleanupScheduleUpdate`; verified 0/negative now raise ValidationError while partial updates still work.
- **File:** backend/app/schemas.py:436-441 (exploited via backend/app/routers/cleanup_schedules.py:95-120)
- **Issue:** `CleanupScheduleUpdate` drops the `ge=1` bounds that `CleanupScheduleCreate` has. A PUT with `capture_retention_days: 0` is accepted; `retention.py:98` computes `cutoff = now - timedelta(days=0)` and the next cron run deletes **every capture** (and with `timelapse_retention_days: 0`, every timelapse) for the profile. Borderline SEV-1: it is a one-keystroke path to irreversible data loss, gated only by user input.
- **Evidence:** `capture_retention_days: int | None = None` / `timelapse_retention_days: int | None = None` in Update vs `Field(default=32, ge=1)` in Create. Verified in source.
- **Suggested fix:** Mirror Create's bounds: `Field(default=None, ge=1)` on both fields in `CleanupScheduleUpdate`.
- **Verification:** PUT a schedule with `capture_retention_days: 0` → assert 422; existing retention tests still pass.

### [SEV-3] F-2: Orphan-record sweep bulk-deletes rows when the captures tree is merely unreadable
- **File:** backend/app/services/retention.py:129-155
- **Issue:** The DB→disk orphan sweep trusts `os.path.exists`. If a profile's capture tree becomes untraversable while the DB stays writable — and this deployment has a **documented recurring failure mode** where Unraid re-chowns appdata out from under the app — every row for the profile "looks" orphaned and is bulk-DELETEd. Files survive but all capture/timelapse records are permanently lost. Marked SEV-3 rather than SEV-1 because the full read-only case also breaks the DB commit (rows survive); partial-permission cases do not.
- **Evidence:** `orphan_capture_ids = [cid for cid, fpath in capture_rows if not os.path.exists(...)]` followed by unconditional `db.execute(delete(Capture)...)`. No sanity threshold. Verified in source.
- **Suggested fix:** Abort the sweep (log an error) when `DATA_DIR/captures/<profile>` itself is missing/unreadable, or when more than e.g. 50% of rows appear orphaned in one pass.
- **Verification:** `chmod 000` a profile's captures dir, run cleanup, assert rows are not deleted and a warning is logged.

### [SEV-3] F-3: Delete endpoints unlink media before committing the DB row
- **File:** backend/app/routers/captures.py:86-103, backend/app/routers/timelapses.py:137-155
- **Issue:** Files are removed **before** `db.commit()`. If the commit fails (the read-only-DB scenario has actually occurred on this deployment), the media is gone but the rows survive as ghosts whose image/video endpoints 404. This is the exact inverse of the ordering rationale documented in profiles.py:105-108.
- **Evidence:** `_safe_remove(...); db.delete(capture); db.commit()` — verified in source for single, bulk, and timelapse variants.
- **Suggested fix:** Delete rows and commit first, then unlink files (a failed unlink leaves a recoverable orphan file; the sweep in F-2 — once guarded — reclaims it).
- **Verification:** Make the DB read-only, issue a delete, confirm files untouched and an error is returned.

### [SEV-3] F-4: Ephemeral SECRET_KEY silently makes encrypted stream URLs unrecoverable
- **File:** backend/app/config.py:19-26
- **Issue:** When `LAPSORA_SECRET_KEY` is unset the app logs a warning and continues with a per-boot random key, so every stream URL/credential written during that run is permanently undecryptable after restart. Migration `004_clear_stale_encrypted_urls.sql` (`UPDATE streams SET url = '';`) is the historical proof this already destroyed data once.
- **Evidence:** `self.SECRET_KEY = secrets.token_hex(32)` after a mere `logging.warning`. Verified in source.
- **Suggested fix:** Persist the generated key to a file under `DATA_DIR` on first boot and reuse it thereafter (env var still takes precedence).
- **Verification:** Boot twice without the env var; a stream created on boot 1 must still decrypt on boot 2.

### [SEV-3] F-5: SQLite runs without WAL or busy_timeout despite concurrent writers
- **File:** backend/app/database.py:13-30
- **Issue:** The connect listener sets only `PRAGMA foreign_keys=ON`. Writers are genuinely concurrent (sync routers in FastAPI's threadpool, AsyncIOScheduler capture/cleanup jobs, the generation worker), so a long retention DELETE holding the write lock can surface as `database is locked` capture failures and stalled requests.
- **Evidence:** `create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)`; listener executes one pragma. Verified in source.
- **Suggested fix:** In the same listener execute `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`. (Python change, not a migration — the semicolon-split runner gotcha does not apply.)
- **Verification:** Run a cleanup deleting ~50k captures while a 5s-interval profile captures; no lock errors, no missed ticks; `PRAGMA journal_mode` returns `wal`.

### [SEV-3] F-6: `DROP COLUMN` migration is not replay-tolerant → potential boot loop
- **File:** backend/app/migrations/versions/018_drop_heatmap_opacity.sql + backend/app/migrations/runner.py:54-62
- **Issue:** In the documented partial-failure scenario (DDL autocommits, then the `_migrations` INSERT fails — e.g. volume flips read-only), the next boot re-runs `ALTER TABLE ... DROP COLUMN heatmap_opacity` and fails with "no such column", which is not in the runner's tolerated-error list ("duplicate column name" / "already exists"). Boot-loops until a manual `_migrations` row insert.
- **Evidence:** `if "duplicate column name" in msg or "already exists" in msg:` — verified; 018 is the only DROP COLUMN migration.
- **Suggested fix:** Add `"no such column"` to the tolerated messages (same convergence rationale already documented in the runner).
- **Verification:** Unit test in test_migration_runner.py applying 018's statement twice through the runner; converges.

- **Related negative check:** a state-machine scan of all 29 migration files found **no** semicolons inside comments or string literals (the known runner gotcha has no current violations), and no model↔migration schema drift.

### [SEV-3] F-7: Retention never deletes timelapse thumbnails
- **File:** backend/app/services/retention.py:112-126, 146-155
- **Issue:** Age-based deletion unlinks `tl.file_path` but never `tl.thumbnail_path` (the router delete endpoints remove both), and the orphan sweep ignores thumbnails too. Since there is no disk→DB sweep, thumbnails leak on disk forever.
- **Evidence:** `_safe_unlink(tl_abs); db.delete(tl)` with no thumbnail handling — verified in source vs routers/timelapses.py:141-142.
- **Suggested fix:** Unlink `tl.thumbnail_path` in the age-based delete, and select/unlink it in the orphan sweep.
- **Verification:** Age a timelapse past retention, run cleanup, assert `*_thumb.jpg` is gone.

### [SEV-3] F-8: Capture error paths leave orphan JPEGs that nothing reclaims
- **File:** backend/app/services/capture.py:336-357, 465-477
- **Issue:** On ffmpeg non-zero exit, on capture timeout, and on any exception after the frame file is written (resize failure, DB commit failure), the partial/unregistered JPEG stays on disk with no DB row. The orphan sweep only works DB→disk, so these accumulate forever.
- **Evidence:** `if proc.returncode != 0: ... return` with no `os.remove(abs_path)`, unlike the corrupt-frame branch at 364-365.
- **Suggested fix:** Unlink `abs_path` in the error/timeout return paths and in the outer `except`.
- **Verification:** Force an ffmpeg failure after file pre-creation (or mock resize to raise); no stray .jpg remains.

### Correctness — backend

### [SEV-2] F-9: Manual disable is undone by health auto-recovery (`auto_disabled` never cleared)
- **FIXED:** Clear `auto_disabled = False` in `enable_profile`, `disable_profile`, and `update_profile` (when `enabled` is in the payload), so a deliberate user toggle overrides the health auto-disable marker.
- **File:** backend/app/routers/profiles.py:126-153 + backend/app/services/health.py:44-57
- **Issue:** `disable_profile` sets `enabled=False` but leaves a stale `auto_disabled=True` (set earlier by health). When the stream recovers, health re-enables **every** `auto_disabled` profile — including ones the user deliberately disabled. The stale flag also makes capture-gap alerting skip the profile and renders the UI badge wrong after manual enable.
- **Evidence:** Verified in source: neither `enable_profile` nor `disable_profile` touches `auto_disabled`; health.py filters `Profile.auto_disabled.is_(True)` and sets `enabled = True`.
- **Suggested fix:** Clear `auto_disabled = False` in `enable_profile`, `disable_profile`, and in `update_profile` when `enabled` is explicitly set.
- **Verification:** Auto-disable a profile (fail health checks), manually disable it, restore the stream → profile must stay disabled.

### [SEV-2] F-10: PrusaLink stop path + health recovery re-enables a managed profile forever
- **FIXED:** Clear `auto_disabled = False` in the PrusaLink `_reconcile` start and stop paths, so once a print ends the managed profile is not marked auto-disabled and health recovery can't re-enable it. (Did NOT exclude managed profiles from health re-enable as the report suggested — that would regress the legitimate mid-print stream-recovery case where captures should resume; clearing the flag on stop is the correct minimal fix.)
- **File:** backend/app/services/prusalink.py:336-342 + backend/app/services/health.py:44-57
- **Issue:** Same root flaw as F-9, different actor: prusalink's stop path sets `profile.enabled = False` without clearing `auto_disabled`. Sequence: stream flaps mid-print (health sets `auto_disabled=True`), print finishes (prusalink disables, flag stays), stream recovers → health re-enables the managed profile and re-adds its capture job, which nothing removes until the *next* print finishes. Endless captures with no print running.
- **Evidence:** Verified in source: `profile.enabled = False` at prusalink.py:339 with `auto_disabled` untouched.
- **Suggested fix:** Clear `auto_disabled` in prusalink's start/stop paths, **and** exclude `managed_by == "prusalink"` profiles from health's auto re-enable (defense in depth).
- **Verification:** Unit test the sequence (unhealthy during print → print finish → recovery); assert profile stays disabled and no `capture_<id>` job exists.

### [SEV-2] F-11: `deflicker == "off"` copies every frame synchronously on the event loop
- **FIXED:** Wrapped the deflicker-off copy loop in `asyncio.to_thread`, mirroring the `deflicker_frames` branch, so multi-thousand-frame jobs no longer block the event loop.
- **File:** backend/app/services/timelapse.py:590-594
- **Issue:** The off-branch runs `shutil.copy2` in a plain loop inside the async generation coroutine, while the on-branch correctly uses `asyncio.to_thread`. A multi-thousand-frame job freezes the API and stalls APScheduler capture ticks (default misfire grace silently skips them) for the duration of the copy.
- **Evidence:** Verified in source: `for src, dst in zip(...): _shutil.copy2(src, dst)` directly in the coroutine.
- **Suggested fix:** Wrap the copy loop in `asyncio.to_thread`, mirroring the `deflicker_frames` call below it.
- **Verification:** Generate with deflicker=off over several thousand captures; API stays responsive, capture jobs fire on schedule.

### [SEV-3] F-12: Generate endpoint returns 202 for nonexistent profiles
- **File:** backend/app/routers/timelapses.py:63-101
- **Issue:** `POST /profiles/{profile_id}/timelapses/generate` never checks the profile exists (no DB dependency at all). Any id returns 202 "queued"; the failure surfaces minutes later as a "No captures found" failure notification. Also the concrete backend half of frontend finding F-27's failure mode.
- **Suggested fix:** `db.get(Profile, profile_id)` + 404 before enqueueing.
- **Verification:** POST to a nonexistent id → 404 instead of 202.

### [SEV-3] F-13: Fixed 5-minute ffmpeg timeout kills large CPU encodes
- **File:** backend/app/services/timelapse.py:318, 835
- **Issue:** `FFMPEG_TIMEOUT = 300` is a hard cap. A yearly render (tens of thousands of frames), especially `libx265` on the lossless CPU path, routinely exceeds 5 minutes — every such generation is killed and reported failed.
- **Suggested fix:** Scale the timeout with `frame_count` (base + per-frame budget) or make it a setting.
- **Verification:** Encode ~10k 1080p frames with h265 lossless on CPU; completes instead of "ffmpeg encode timed out".

### [SEV-3] F-14: Motion blur loads the entire frame set into RAM
- **File:** backend/app/services/timelapse.py:257-262 (`apply_motion_blur`)
- **Issue:** All frames are decoded and appended to a list up front (~6 MB per 1080p frame ⇒ a few thousand frames is 20-60 GB) — an OOM kill of the whole app, taking capture down with it.
- **Suggested fix:** Keep a sliding window of `blend_count` decoded frames (deque), writing to temp names to avoid re-reading blended output.
- **Verification:** motion_blur=high over a few thousand frames while watching container RSS; flat memory profile, identical output on a small set.

### [SEV-3] F-15: Late cancel after encode still commits the timelapse
- **File:** backend/app/services/generation_queue.py:141-153 + backend/app/services/timelapse.py:853-957
- **Issue:** `generate_timelapse` never checks the cancel event after the encode step, so cancelling during finalize (ffprobe/thumbnail/commit) yields both a "cancelled" API response and a finished timelapse.
- **Suggested fix:** Call `_check_cancel()` at the start of the finalize step (before the DB insert) so a late cancel routes through the existing `GenerationCancelled` cleanup.
- **Verification:** Cancel via API while finalize runs; no Timelapse row is created and partial files are removed.

### [SEV-3] F-16: Credentialed URLs leak into logs and persisted notifications
- **File:** backend/app/services/http_source.py:63-68, backend/app/services/providers.py:89-90, backend/app/services/rtsp.py:96-99 (flowing into capture.py:249-260, 343-357)
- **Issue:** The HTTP retry warning logs the plaintext URL; httpx `HTTPStatusError` messages embed the full URL (userinfo included); ffmpeg stderr for RTSP contains the credentialed URL — all of which flow into `capture_failure` event bodies persisted to the notifications table and dispatched via Apprise (which may leave the LAN).
- **Suggested fix:** Redact userinfo (reuse the `url_masked` logic from models.py) before logging/raising, and scrub URLs from ffmpeg stderr before embedding in event bodies.
- **Verification:** Configure a stream with `http://user:pass@host/…`, force a failure, grep logs + notifications table for the password.

### [SEV-3] F-17: Subprocess timeout paths in finalize never kill the child
- **File:** backend/app/services/timelapse.py:862-899
- **Issue:** The ffprobe and thumbnail-ffmpeg blocks catch bare `Exception` (swallowing `TimeoutError`) without `_kill`, unlike every other subprocess call in the codebase — a hung child leaks a process per generation.
- **Suggested fix:** Catch `TimeoutError` explicitly and `await _kill(proc)` in both blocks, mirroring capture.py:337-342.
- **Verification:** Point ffprobe at a FIFO; no lingering process after the 30s timeout.

### [SEV-3] F-18: App shutdown never stops the generation worker or active ffmpeg
- **File:** backend/app/main.py:69-75, backend/app/services/generation_queue.py
- **Issue:** Lifespan shutdown stops only the scheduler; the worker task and any active ffmpeg subprocess are never cancelled/awaited (`start_worker` exists, no stop). Relies on process teardown; produces orphaned ffmpeg / "Task was destroyed but it is pending" on restart mid-render.
- **Suggested fix:** Add a `stop_worker()` that cancels `_worker_task` and terminates the active proc; call it in lifespan shutdown.
- **Verification:** Stop uvicorn mid-render; clean exit, no orphaned ffmpeg.

### [SEV-3] F-19: Capture-gap alert fires falsely when an active window opens
- **File:** backend/app/services/capture_gap.py:63-73
- **Issue:** The gap is measured as `now − last_capture` across window-closed time: the first hourly check after a sun/manual window opens (before the day's first frame) sees yesterday's last capture and fires a false "capture gap" alert; suppression resets on the first success so this can recur daily.
- **Suggested fix:** Clamp the gap start to the window-open time, or skip when the window opened less than `threshold_seconds` ago.
- **Verification:** Manual-window profile opening minutes before the hourly check with yesterday's captures present; no alert at window open.

### PrusaLink lifecycle

### [SEV-3] F-20: Disable-during-poll TOCTOU can leave a permanently open print + endless captures
- **File:** backend/app/services/prusalink.py:373-388 + backend/app/routers/settings.py:386-402
- **Issue:** `poll_printer` checks `cfg["enabled"]` once, then awaits `get_status` (up to 5s). Disabling via PUT in that window removes the poll job and cancels the open PrintJob — then the resuming poll sees no open job, recreates one, re-enables the managed profile, and adds a capture job. No poller remains to ever close it.
- **Suggested fix:** Re-read enabled/stream_id from the DB inside `_reconcile` (after the await) before acting on the start branch.
- **Verification:** Stub `get_status` to block, flip enabled=False mid-poll, assert no new PrintJob/profile enable.

### [SEV-3] F-21: No job-id dedupe — back-to-back prints merge into one PrintJob
- **File:** backend/app/services/prusalink.py:289-293
- **Issue:** Transition detection is by state edge only; `status["job_id"]` is stored but never compared, so two consecutive prints that never show a non-PRINTING state within one poll interval merge into a single PrintJob/timelapse with the first print's gcode name.
- **Suggested fix:** When a job is open, state is printing, and `status["job_id"]` differs from `pj.prusalink_job_id`, treat as finish-then-start.
- **Verification:** Unit test: open pj with job_id=1, poll PRINTING with job_id=2 → old closed, new created.

### [SEV-3] F-22: Printer unreachable mid-print leaves the job and capture profile running forever
- **File:** backend/app/services/prusalink.py:190-194, 380-382
- **Issue:** `get_status` returns None on any error and the poll early-returns, so a printer powered off mid-print (called "normal" in the code's own comment) never reconciles: open PrintJob and enabled managed capture profile persist indefinitely.
- **Suggested fix:** Track consecutive unreachable polls; cancel-close the open print and stop capture after a grace period.
- **Verification:** Open pj, force `get_status` → None repeatedly; job closed and capture job removed after the threshold.

### [SEV-3] F-23: Password decrypt failure silently degrades to empty password + warn-loop
- **File:** backend/app/services/prusalink.py:219-226
- **Issue:** Decrypt failure logs a warning and proceeds with `password=""`; digest auth then fails, `get_status` returns None (debug level), and print tracking silently stops while the warning fires every poll and on every settings read.
- **Suggested fix:** Treat decrypt failure as unconfigured (return None from `get_config`) and surface a persistent unhealthy state.
- **Verification:** Corrupt the stored password setting, restart; integration reports unconfigured instead of warn-looping.

### Reliability — integrations & services

### [SEV-3] F-24: HA and weather fetch failures have no negative caching → per-capture timeout storms
- **File:** backend/app/services/homeassistant.py:35-54, backend/app/services/weather.py:56-80
- **Issue:** While HA/Open-Meteo is down, every capture (per profile, per interval) blocks up to the 10s timeout and logs a full traceback — on short intervals this can eat most of the capture budget.
- **Suggested fix:** Cache failures with a short TTL (30-60s) or exponential backoff; drop `exc_info` to one-line warnings.
- **Verification:** Point HA at a black-holed IP with two 5s-interval profiles; one probe per TTL, not per capture.

### [SEV-3] F-25: Blocking DB (and PIL) work inside `async def` settings handlers
- **File:** backend/app/routers/settings.py:184-189, 275-300, 349-405, 438-449 (pattern)
- **Issue:** Handlers that must be async (they await health probes) run sync SQLAlchemy/SQLite calls — and in `upload_logo`, PIL encode — directly on the event loop. Under SQLite lock contention one stuck query stalls the entire loop, including SSE and all APScheduler asyncio jobs. Largely mitigated if F-5 (busy_timeout/WAL) lands, but the pattern remains.
- **Suggested fix:** Move DB work to `asyncio.to_thread`, or split sync reads from the awaited probes.
- **Verification:** Hold a write transaction open in a second connection; settings GETs must not freeze unrelated endpoints.

### [SEV-3] F-26: Deflicker treats unreadable frames as brightness 0.0, darkening neighbors
- **File:** backend/app/services/deflicker.py:81, 91
- **Issue:** Unreadable frames are recorded as 0.0 but still feed the Gaussian smoothing, so the target curve dips toward black around a missing frame and adjacent good frames get visibly darkened.
- **Suggested fix:** Interpolate brightness for unreadable indices from readable neighbors (`np.interp`) before smoothing.
- **Verification:** Unit test: constant-brightness frames with one unreadable path; neighbor output within ~1% of input.

- **Related (same file, SEV-3):** the CuPy branches (deflicker.py:22-32, 107-111) have no runtime fallback — a mid-run CUDA OOM/context error fails the whole generation instead of degrading to the numpy path. Wrap in try/except that falls through to CPU.
- **Related (hdr.py, SEV-3):** the 15s `-skip_frame nokey` grab is GOP-dependent (long-GOP cameras time out), and `range(1, 4)` errors on a missing `frame_3.jpg` when ffmpeg exits 0 with fewer frames — glob what was written and fuse what exists.

### Correctness — frontend

### [SEV-3] F-27: Malformed custom time in GenerateDialog silently generates over the entire history
- **File:** frontend/src/lib/components/GenerateDialog.svelte:289-311 + frontend/src/lib/utils.ts:66-73
- **Issue:** Time fields are free text; `localToUtcNaive` returns `''` for anything not `^\d{2}:\d{2}$` (e.g. "8:00"), and submit sends `period_start: period_start || undefined` → backend treats it as unbounded. The user asked for one hour and gets a full-history render queued.
- **Suggested fix:** Validate the custom range before submit (inline error) or use `type="time"` inputs.
- **Verification:** Enter "8:00" as start → error, not a queued job.

### [SEV-3] F-28: Duplicate-profile drops `ir_only`, `ir_chroma_threshold`, `ha_sensors`
- **File:** frontend/src/routes/streams/[id]/+page.svelte:257-281
- **Issue:** The duplicate payload copies every field except these three (all present on `ProfileCreate` in both frontend types and backend schema), silently producing a behaviorally different copy.
- **Suggested fix:** Add the three fields to the payload.
- **Verification:** Duplicate an IR-only profile with HA sensors; copy retains them.

### [SEV-3] F-29: Live view (MSE) never evicts buffer and swallows append errors → eventual freeze
- **File:** frontend/src/lib/components/MsePlayer.svelte:23-33
- **Issue:** `sourceBuffer.remove()` is never called and `appendBuffer` failures hit an empty `catch`, so a long-running live view hits the MSE quota and freezes with status stuck on 'playing'.
- **Suggested fix:** On `updateend`, trim buffered ranges older than ~30s behind `currentTime`; surface repeated append failures as `status = 'error'`.
- **Verification:** Leave live view running 30+ min; playback continues.

### [SEV-3] F-30: Shift-click range after paging selects unintended rows (feeds bulk delete)
- **File:** frontend/src/routes/files/+page.svelte:177-187, 50-65
- **Issue:** `changePage` clears neither selection nor `lastClickedCaptureIdx`, so a shift-click on page 2 ranges against a page-1 index and selects unintended rows — which bulk delete then deletes.
- **Suggested fix:** Reset the last-clicked indices (and ideally clear selection) in `changePage`.
- **Verification:** Select idx 20 on page 1, page forward, shift-click idx 3 → only 0-3 selected.

### [SEV-3] F-31: Timelapse lists silently capped at 50 with no pagination
- **File:** frontend/src/routes/timelapses/+page.svelte:48-60, frontend/src/routes/files/+page.svelte:169-175 (backend default: routers/timelapses.py:44)
- **Issue:** Both pages use the backend default `limit=50` with no pagination UI — the 51st-and-older timelapses are unreachable from the UI.
- **Suggested fix:** Add pagination or pass an explicit higher limit.
- **Verification:** With 51+ timelapses, all reachable.

- **Related (latent, SEV-3):** `handle_event`'s persisted-path SSE payload drops the `data` dict (notifications.py:80-87), so `generation_id` never reaches the frontend's `clearActiveGeneration`; correct today only because the queue is serial. Include `**(data or {})` in the payload.
- **Related (SEV-3):** CapturePreview.svelte:89-102 dereferences `current.id`/`current.captured_at` in markup without the `{#if current}` guard the script explicitly notes is required — crashes if `captures` shrinks below `index`.

### Tests

### [SEV-2] F-32: Two data-integrity tests delete directories under the real DATA_DIR
- **FIXED:** Both tests now `patch.object(settings, "DATA_DIR", str(tmp_path))` around their setup and the delete call, so they can never touch the real capture archive. (Left the broader conftest env-var hardening as a deferred follow-up — see Fix Session Summary.)
- **File:** backend/tests/test_data_integrity.py:43-69
- **Issue:** `test_delete_profile_removes_media_dirs` / `test_delete_stream_removes_media_dirs` use `settings.DATA_DIR` unpatched; the in-memory test DB always yields id 1, so the API call recursively deletes `backend/data/captures/1` — real captured media if present. The documented test recipe (only `LAPSORA_DATABASE_URL` set) leaves DATA_DIR pointing at the real directory.
- **Evidence:** No monkeypatch, unlike test_delete_robustness.py:53 which patches DATA_DIR.
- **Suggested fix:** Monkeypatch `settings.DATA_DIR` to `tmp_path` in these tests; longer-term, have conftest set `LAPSORA_DATA_DIR`/`LAPSORA_DATABASE_URL` to tmp paths before any `app.*` import (the `client` fixture currently runs the full lifespan — migrations, `restore_jobs`, health/watchdog/prusalink jobs — against the real engine).
- **Verification:** Seed a sentinel file in `backend/data/captures/1/`, run the suite; sentinel survives.

### [SEV-3] F-33: Suite is red without network/at certain hours — 4 failing tests
- **File:** backend/tests/test_homeassistant.py:70-87; backend/tests/test_scheduler.py:32-60
- **Issue:** (a) Two HA tests assert `connected is True` but the endpoint performs a real HTTP probe to `http://ha.local:8123` / `http://b` — verified failing (~10s timeout each) on any machine without those hosts. (b) `test_compute_start_date_*` derive windows from wall-clock; between 00:00-02:00 local the `now − 2h` strftime wraps to yesterday and the assertion fails — verified at 01:01.
- **Suggested fix:** Stub `health_status.reachable` as test_prusalink.py:120-126 already does; inject/freeze the clock in scheduler tests instead of deriving from `datetime.now()`.
- **Verification:** `pytest` offline and at 01:00 → 0 failures.

### [SEV-3] F-34: No test dependencies or pytest config declared; CI never runs tests
- **File:** backend/pyproject.toml; .github/workflows/docker-publish.yml
- **Issue:** pytest/pytest-asyncio appear nowhere in the repo; ~20 `@pytest.mark.asyncio` tests depend on the unpinned `.venv` happening to have pytest-asyncio (without it they skip-with-warning, silently shrinking the suite). The only CI workflow builds Docker images and never runs the suite.
- **Suggested fix:** Add a dev dependency group + `[tool.pytest.ini_options]` with `asyncio_mode`; add a test job to CI.
- **Verification:** Fresh venv from pyproject → full suite runs; CI fails on a broken test.

### [SEV-3] F-35: Critical-path coverage gaps (ranked)
- **File:** gap: multiple modules
- **Issue / Suggested fix / Verification (per gap):**
  1. **retention.py timelapse paths** — all retention tests seed only Capture rows; the timelapse age-delete and orphan scan are unasserted. Retention is the highest data-loss surface in the app. Mirror the capture tests with Timelapse rows. (Inverting the timelapse cutoff comparison passes the suite today.)
  2. **generation_queue `_worker`/`start_worker`** — the worker loop (dequeue, cancelled-skip cleanup, `task_done` accounting, crash-restart) has zero tests; the existing test's docstring claims behavior it never drives. Add an asyncio test with a stubbed `generate_timelapse`.
  3. **RTSP branch of capture** — the product's core path has no tests (capture tests cover only the bytes-source branch). Test the dispatch/failure handling with `rtsp.grab_frame` stubbed.
  4. **health.check_all_streams** — auto-disable/re-enable (the F-9/F-10 machinery) has zero tests.
  5. **prusalink poll wrapper** — only the pure `_reconcile` layer is tested; the fetch/except path (printer flap mid-print) is not.
  6. **migration runner semicolon-split** — the documented gotcha that already bit once has no regression test.

### Hygiene (SEV-4)

### [SEV-4] F-36: Missing validation bounds (batch)
- **File:** backend/app/schemas.py + routers
- **Issue / fix per item:**
  - schemas.py:78-80 — `PrusaLinkConfig` allows `min_interval_seconds > max_interval_seconds`; add a model validator.
  - schemas.py:509-512 — `HealthConfig.failure_threshold` / `low_disk_threshold_percent` unbounded; `0` mass-auto-disables on first transient failure. Add `ge=1` / `ge=1, le=99`.
  - schemas.py:360 — `lookback_hours` accepts negatives → future start → guaranteed "No captures found". Add `ge=1`.
  - schemas.py:290 + timelapse.py:730-733 — `TimelapseGenerate.format` is interpolated into the output filename unvalidated ("/" or ".." escapes the dir; unknown formats silently encode as h264 with a bogus extension). Constrain with `Literal["mp4","webm","gif","mkv"]`.
  - routers/captures.py:31-53 — `limit`/`offset` lack lower bounds (`limit=-1` = SQLite unbounded). Add `ge=1`/`ge=0` to match the other list endpoints.
- **Verification:** 422 on each invalid payload.

### [SEV-4] F-37: Timelapse period end at 23:59:59 drops final-second captures
- **File:** backend/app/services/timelapse.py:333-352
- **Issue:** Inclusive `23:59:59` bound excludes microsecond-timestamped captures in the last second of daily/weekly/monthly/yearly periods.
- **Suggested fix:** Exclusive `< next-period-start` bound.
- **Verification:** Capture at 23:59:59.5 included in the daily render.

### [SEV-4] F-38: PrusaLink poll job starts without a stored password
- **File:** backend/app/routers/settings.py:386-389
- **Issue:** The job is gated on `enabled and url and stream_id` but not the `configured` predicate (password present), so enabling before entering credentials starts a poll loop that fails auth every interval.
- **Suggested fix:** Gate on the same `configured` predicate used by `_read_prusalink`. Also: the disable path (settings.py:394-402) closes only `.first()` open PrintJob — close `.all()`.

### [SEV-4] F-39: Preset silently overwrites explicit cron on schedule update
- **File:** backend/app/routers/timelapse_schedules.py:156-165
- **Issue:** A PUT supplying both `preset` and `cron_expression` has the user's cron overwritten by the preset's; clearing preset leaves the old preset's cron.
- **Suggested fix:** Only derive cron from preset when `cron_expression` is absent from the payload.

### [SEV-4] F-40: Swallowed/blank error paths (batch)
- **File:** various
- **Issue / fix per item:**
  - services/health.py:97-100 — per-stream handler doesn't `db.rollback()`, poisoning the session for subsequent streams in the run. Add rollback.
  - services/providers.py:70-90 — Fernet `InvalidToken` stringifies to `""`, so decrypt failures surface as a blank test-endpoint message (the likely symptom of F-4). Catch it and say "Stored URL cannot be decrypted (SECRET_KEY changed?)".
  - services/gpu.py:19-24 — `detect_nvidia_gpu` lets `PermissionError`/`OSError` propagate; broaden to `except OSError`.
  - services/http_source.py:100-115 — MJPEG grab has per-read and byte bounds but no overall deadline; wrap in `asyncio.timeout(30)`.

### [SEV-4] F-41: Docker/deploy friction (batch)
- **File:** docker/
- **Issue / fix per item:**
  - entrypoint.sh:2 — unconditional `chown -R /app/data` walks the whole archive every start; guard on the root dir's owner.
  - docker-compose.yml:14-15 — `env_file: ../.env` is mandatory; fresh clones fail. Use `required: false` long form.
  - Dockerfile:40-41 — `COPY backend/ ./` before `pip install` invalidates the dependency layer on every source change; copy `pyproject.toml` first.

### [SEV-4] F-42: Retention hydrates full ORM rows for age-based deletes
- **File:** backend/app/services/retention.py:99-109
- **Issue:** A first-ever cleanup of a long-running profile holds hundreds of MB; the orphan sweep already shows the id/path-tuple pattern.
- **Suggested fix:** Select `(id, file_path)` and delete by id chunks. Also: the empty-dir sweep (163-173) can rmdir a just-created date dir before ffmpeg writes the first frame — skip dirs younger than a few minutes.

### [SEV-4] F-43: Deflicker re-encodes at quality 85 while the rest of the pipeline uses 95
- **File:** backend/app/services/deflicker.py:51 + backend/app/services/timelapse.py:596
- **Issue:** The only caller never passes `quality`, making deflicker the silent quality bottleneck.
- **Suggested fix:** Pass `quality=95` (or the profile quality) from timelapse.py.

### [SEV-4] F-44: Dead code (verified by tracing usage)
- **File:** various
- **Items:** `api.getProfile` (frontend/src/lib/api.ts:44) unused; `available_icons()` (backend/app/services/sensor_icons.py:11-13) only referenced by its own test while ProfileForm.svelte hardcodes a duplicate icon list that can silently drift — either expose via API or delete and document the sync requirement; `projectionDays` (frontend/src/routes/statistics/+page.svelte:162-172) computes values it discards; `bulkDeleteTarget` fields (files/+page.svelte:84-88) set but ignored.

### [SEV-4] F-45: Frontend polish (batch)
- **File:** frontend/src
- **Items:** stream-detail caption says "5 seconds", interval is 15000ms (streams/[id]/+page.svelte:375 vs 137); StreamCard 30s preview polling keeps firing in hidden tabs (each tick is a server-side frame grab) — add the `document.hidden` guard the detail page has; StorageStats "free" segment includes non-Lapsora disk usage, contradicting its own tooltip — compute from `disk_free_bytes/disk_total_bytes`; `formatInterval(90)` renders "2m" (utils.ts:43-47); GenerateDialog preset ranges are `$derived` snapshots of dialog-open time (stale "now" on late submit) and with zero profiles submits to `/profiles/0/...` (guard empty options); partial bulk-delete failure leaves stale selection entries (files/+page.svelte:90-109); ScheduleManager/CleanupScheduleManager still do the per-stream `getStreamProfiles` N+1 that other pages were already migrated off; `_use24h` module global is set after first paint so early-rendered timestamps stay 12h; weather overlay 'minimal' style draws RGBA fill on an RGB image (alpha ignored → solid black) and `weather_code or 0` labels missing data "Clear sky"; sensor/weather overlay `_anchor` lacks the `max(0, …)` clamp logo_overlay has; hdr.py imports private `_kill` from rtsp.py.

## Summary table (sorted by severity)

| ID | Sev | Title | File |
|----|-----|-------|------|
| F-1 | SEV-2 | Cleanup update accepts 0-day retention → mass deletion | schemas.py:436 |
| F-9 | SEV-2 | Manual disable undone by health auto-recovery | routers/profiles.py:141 |
| F-10 | SEV-2 | PrusaLink stop + recovery re-enables managed profile | services/prusalink.py:336 |
| F-11 | SEV-2 | deflicker=off copies frames on the event loop | services/timelapse.py:590 |
| F-32 | SEV-2 | Tests delete dirs under the real DATA_DIR | tests/test_data_integrity.py:43 |
| F-2 | SEV-3 | Orphan sweep bulk-deletes rows on unreadable tree | services/retention.py:129 |
| F-3 | SEV-3 | Delete endpoints unlink media before commit | routers/captures.py:86 |
| F-4 | SEV-3 | Ephemeral SECRET_KEY destroys encrypted URLs | config.py:19 |
| F-5 | SEV-3 | No WAL/busy_timeout on SQLite | database.py:25 |
| F-6 | SEV-3 | DROP COLUMN migration not replay-tolerant | migrations/versions/018 |
| F-7 | SEV-3 | Retention never deletes timelapse thumbnails | services/retention.py:112 |
| F-8 | SEV-3 | Capture error paths leak orphan JPEGs | services/capture.py:336 |
| F-12 | SEV-3 | Generate returns 202 for nonexistent profiles | routers/timelapses.py:63 |
| F-13 | SEV-3 | Fixed 5-min ffmpeg timeout kills large encodes | services/timelapse.py:318 |
| F-14 | SEV-3 | Motion blur loads all frames into RAM | services/timelapse.py:257 |
| F-15 | SEV-3 | Late cancel after encode still commits | generation_queue.py:141 |
| F-16 | SEV-3 | Credentialed URLs leak into logs/notifications | http_source.py:63 et al. |
| F-17 | SEV-3 | Finalize subprocess timeouts never kill child | services/timelapse.py:862 |
| F-18 | SEV-3 | Shutdown never stops worker/ffmpeg | main.py:69 |
| F-19 | SEV-3 | False capture-gap alert at window open | services/capture_gap.py:63 |
| F-20 | SEV-3 | PrusaLink disable-during-poll TOCTOU | services/prusalink.py:373 |
| F-21 | SEV-3 | No job-id dedupe merges back-to-back prints | services/prusalink.py:289 |
| F-22 | SEV-3 | Unreachable printer leaves print open forever | services/prusalink.py:190 |
| F-23 | SEV-3 | Password decrypt failure → empty-password poll loop | services/prusalink.py:219 |
| F-24 | SEV-3 | No negative caching on HA/weather failures | homeassistant.py:35 |
| F-25 | SEV-3 | Blocking DB/PIL in async settings handlers | routers/settings.py:184 |
| F-26 | SEV-3 | Deflicker zeros + no GPU fallback; HDR brittleness | deflicker.py:81, hdr.py:93 |
| F-27 | SEV-3 | Malformed time → full-history generation | GenerateDialog.svelte:289 |
| F-28 | SEV-3 | Duplicate profile drops IR/HA fields | streams/[id]/+page.svelte:257 |
| F-29 | SEV-3 | MSE player never evicts buffer → freeze | MsePlayer.svelte:23 |
| F-30 | SEV-3 | Cross-page shift-click misselects for bulk delete | files/+page.svelte:177 |
| F-31 | SEV-3 | Timelapse lists capped at 50, no pagination | timelapses/+page.svelte:48 |
| F-33 | SEV-3 | Suite red offline / between 00:00-02:00 | test_homeassistant.py:70 |
| F-34 | SEV-3 | No test deps/config declared; CI runs no tests | pyproject.toml |
| F-35 | SEV-3 | Coverage gaps: retention TL paths, worker, RTSP, health | (gaps) |
| F-36–F-45 | SEV-4 | Validation bounds, docker friction, dead code, polish | (see entries) |

## Top 3 fixes

1. **F-1 + F-2 + F-3 (the deletion cluster).** These are the only paths in the app to *irreversible* loss of captures, and this deployment's documented ops history (Unraid re-chown events, read-only DB incidents) is exactly the environment that triggers F-2 and F-3. All three fixes are small: two `Field(ge=1)` bounds, a sanity guard on the orphan sweep, and swapping unlink/commit order.
2. **F-9 + F-10 (`auto_disabled` lifecycle).** Two independent reviewers converged on this from different directions (manual disable, PrusaLink stop). The failure mode — profiles silently re-enabling and capturing forever — directly corrupts the product's output (garbage frames in timelapses, disk growth) and is invisible until noticed. Fix is a handful of `auto_disabled = False` assignments plus excluding managed profiles from health re-enable.
3. **F-5 + F-32 + F-33 (foundations: SQLite pragmas and a trustworthy test suite).** WAL + busy_timeout removes the most likely cause of future "database is locked" capture failures given concurrent cleanup/capture writers. Making the suite hermetic (stub the HA probe, freeze the clock, tmp DATA_DIR — and stop tests from being able to delete real media) turns the existing 183 tests into a safety net you can actually run before every change, which everything else above depends on.

## Not Reviewed

- `package-lock.json` / generated build output, SVG/PNG/icon assets, LICENSE.
- `docs/superpowers/` plan/spec documents (design docs, not code; in-tree presence vs CLAUDE.md docs rule is known, tracked pending work).
- Runtime/browser verification: this review is static analysis plus one full backend test-suite run (183 passed, 4 failed — see F-33); no Docker build or Chrome DevTools verification was performed, per read-only scope.
- Trilium docs sync was not performed (read-only review; no project changes to document).
- The `caveman`/superpowers tooling directories are session tooling, not project code.
