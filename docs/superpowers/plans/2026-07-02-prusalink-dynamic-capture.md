# PrusaLink Dynamic Per-Print Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static per-profile PrusaLink binding with a camera binding + per-print auto-computed capture interval, per-print `print_jobs` records, and a reworked settings UI.

**Architecture:** PrusaLink binds to a stream; the integration owns a hidden "managed" Profile on that stream (`profiles.managed_by='prusalink'`) so the existing capture/generation pipeline is untouched. The poller reads `time_printing + time_remaining` from PrusaLink status, computes `interval = estimate / (clip_seconds × clip_fps)` clamped to `[min,max]`, and records each print in a new `print_jobs` table (open row = active print; survives restarts). On finish, the render is enqueued with overlay options from settings and named after the gcode file.

**Tech Stack:** FastAPI + SQLAlchemy + APScheduler (backend), SvelteKit 2 / Svelte 5 runes (frontend), SQLite SQL migrations, pytest.

**Spec:** `docs/superpowers/specs/2026-07-02-prusalink-dynamic-capture-design.md`

## Global Constraints

- Never run the app natively; verification via Docker: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build && ... up -d` (GPU override always).
- Backend tests run locally via:
  ```bash
  cd backend && source .venv/bin/activate && \
    rm -rf /tmp/lapsora_test.db /tmp/lapsora_data && mkdir -p /tmp/lapsora_data && \
    LAPSORA_DATABASE_URL="sqlite:////tmp/lapsora_test.db" LAPSORA_DATA_DIR=/tmp/lapsora_data HOME=/tmp \
    python -m pytest -p no:cacheprovider -q <test-file-or-blank>
  ```
  (Known: `test_config::test_settings_defaults` fails under the `LAPSORA_DATA_DIR` override — pre-existing, ignore. A trailing `RuntimeError: <Queue …> is bound to a different event loop` after the summary is harmless shutdown noise.)
- Migration files are plain SQL in `backend/app/migrations/versions/`, auto-applied on startup in filename order. Next number: `029`.
- Defaults (from spec, exact values): `clip_seconds=20`, `clip_fps=25`, `default_interval_seconds=10`, `min_interval_seconds=2`, `max_interval_seconds=120`, `timestamp_overlay=True`, `logo_overlay=False`, `deflicker="medium"`, `quality=90`.
- Managed profile name: `"3D Print (auto)"`; marker value: `managed_by = "prusalink"`.
- Commit after each task. Frontend code style: tabs, Tailwind classes matching the existing settings page.

---

### Task 1: Migration 029 + models (print_jobs, managed_by, timelapse name, cleanup)

**Files:**
- Create: `backend/app/migrations/versions/029_prusalink_dynamic_capture.sql`
- Modify: `backend/app/models.py` (add `PrintJob`; add `Profile.managed_by`; add `Timelapse.name`)
- Test: `backend/tests/test_print_jobs.py` (new)

**Interfaces:**
- Produces: `models.PrintJob` with columns `id, prusalink_job_id (int|None), gcode_name (str), stream_id (FK streams), status (str: printing|finished|cancelled), started_at (datetime), finished_at (datetime|None), estimated_seconds (float|None), interval_seconds (int|None), timelapse_id (FK timelapses, None), created_at`.
- Produces: `Profile.managed_by: str | None`, `Timelapse.name: str | None`.

- [ ] **Step 1: Write failing model test**

Create `backend/tests/test_print_jobs.py`:

```python
"""PrintJob model + print-jobs API coverage."""

from datetime import UTC, datetime

from app.models import PrintJob, Profile, Stream, Timelapse


def _mk_stream(db) -> Stream:
    s = Stream(name="printer-cam", url="rtsp://x", type="rtsp")
    db.add(s)
    db.commit()
    return s


def test_print_job_model_roundtrip(db):
    s = _mk_stream(db)
    pj = PrintJob(
        prusalink_job_id=42,
        gcode_name="benchy.gcode",
        stream_id=s.id,
        status="printing",
        started_at=datetime.now(UTC),
        estimated_seconds=3600.0,
        interval_seconds=7,
    )
    db.add(pj)
    db.commit()
    got = db.query(PrintJob).filter(PrintJob.status == "printing").one()
    assert got.gcode_name == "benchy.gcode"
    assert got.timelapse_id is None
    assert got.finished_at is None


def test_profile_managed_by_and_timelapse_name_columns(db):
    s = _mk_stream(db)
    p = Profile(stream_id=s.id, name="3D Print (auto)", managed_by="prusalink", enabled=False)
    db.add(p)
    db.commit()
    tl = Timelapse(profile_id=p.id, file_path="x.mp4", name="benchy.gcode")
    db.add(tl)
    db.commit()
    assert db.get(Profile, p.id).managed_by == "prusalink"
    assert db.get(Timelapse, tl.id).name == "benchy.gcode"
```

Note: check `Stream`'s required constructor fields in `backend/app/models.py` (top of file) and adjust `_mk_stream` to whatever is non-nullable (other tests, e.g. `backend/tests/test_profiles.py`, already construct Streams — copy their pattern exactly).

- [ ] **Step 2: Run test to verify it fails**

Run (test command from Global Constraints) with `tests/test_print_jobs.py`.
Expected: FAIL — `ImportError: cannot import name 'PrintJob'`.

- [ ] **Step 3: Add models**

In `backend/app/models.py`:

Add to `Profile` (after `ha_sensors`, before `source_template_id`):

```python
    managed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add to `Timelapse` (after `thumbnail_path`):

```python
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add new model after `Timelapse`:

```python
class PrintJob(Base):
    """One 3D print detected via PrusaLink. An open row (status='printing') is
    the source of truth for an in-flight print and survives app restarts."""

    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prusalink_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gcode_name: Mapped[str] = mapped_column(Text, default="")
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, default="printing")  # printing|finished|cancelled
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    estimated_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timelapse_id: Mapped[int | None] = mapped_column(
        ForeignKey("timelapses.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    timelapse: Mapped["Timelapse | None"] = relationship()
```

- [ ] **Step 4: Write migration**

Create `backend/app/migrations/versions/029_prusalink_dynamic_capture.sql`:

```sql
-- PrusaLink dynamic per-print capture: print_jobs table, managed profiles,
-- timelapse names; convert config from profile binding to stream binding;
-- drop the now-obsolete seeded 3D-printing templates and legacy state rows.

CREATE TABLE IF NOT EXISTS print_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prusalink_job_id INTEGER,
    gcode_name TEXT NOT NULL DEFAULT '',
    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'printing',
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    estimated_seconds REAL,
    interval_seconds INTEGER,
    timelapse_id INTEGER REFERENCES timelapses(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status);

ALTER TABLE profiles ADD COLUMN managed_by TEXT;
ALTER TABLE timelapses ADD COLUMN name TEXT;

-- Convert the stored PrusaLink config: profile binding -> that profile's stream.
UPDATE settings SET value = json_set(
    json_remove(value, '$.profile_id', '$.fps', '$.format'),
    '$.stream_id',
    (SELECT p.stream_id FROM profiles p
      WHERE p.id = json_extract(settings.value, '$.profile_id'))
) WHERE key = 'prusalink_config' AND json_valid(value);

-- Obsolete: nothing selects between templates any more.
DELETE FROM profile_templates WHERE is_system = 1 AND category = '3D Printing';

-- Replaced by the open print_jobs row.
DELETE FROM settings WHERE key IN ('prusalink_active', 'prusalink_print_started_at');
```

- [ ] **Step 5: Run tests to verify they pass**

Run `tests/test_print_jobs.py` (model tests use `Base.metadata.create_all`, exercising the models) **and** `tests/test_migration_runner.py` (must still pass — it validates migration file conventions).
Expected: PASS.

- [ ] **Step 6: Verify migration SQL applies to a scratch DB**

```bash
cd backend && python - <<'EOF'
import sqlite3, pathlib
db = sqlite3.connect("/tmp/mig_check.db")
# minimal preexisting schema bits the migration touches
db.executescript("""
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE streams(id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE profiles(id INTEGER PRIMARY KEY, stream_id INTEGER, name TEXT);
CREATE TABLE timelapses(id INTEGER PRIMARY KEY, profile_id INTEGER, file_path TEXT);
CREATE TABLE profile_templates(id INTEGER PRIMARY KEY, name TEXT, category TEXT, is_system INTEGER);
INSERT INTO streams VALUES (1,'cam');
INSERT INTO profiles VALUES (5,1,'old');
INSERT INTO settings VALUES ('prusalink_config','{"profile_id":5,"fps":24,"format":"mp4","enabled":true}');
INSERT INTO settings VALUES ('prusalink_active','true');
INSERT INTO profile_templates VALUES (1,'3D Print - Standard','3D Printing',1);
""")
db.executescript(pathlib.Path("app/migrations/versions/029_prusalink_dynamic_capture.sql").read_text())
row = db.execute("SELECT value FROM settings WHERE key='prusalink_config'").fetchone()
print("config:", row)
assert '"stream_id":1' in row[0].replace(" ", "") and "profile_id" not in row[0]
assert db.execute("SELECT COUNT(*) FROM profile_templates WHERE category='3D Printing'").fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM settings WHERE key='prusalink_active'").fetchone()[0] == 0
print("migration OK")
EOF
rm -f /tmp/mig_check.db
```

Expected output ends with `migration OK`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/migrations/versions/029_prusalink_dynamic_capture.sql backend/tests/test_print_jobs.py
git commit -m "feat(prusalink): print_jobs table, managed profiles, timelapse names (migration 029)"
```

---

### Task 2: Pure logic — interval computation + richer status parsing

**Files:**
- Modify: `backend/app/services/prusalink.py` (replace `DEFAULT_CONFIG`; extend `parse_status`; add `compute_interval`)
- Test: `backend/tests/test_prusalink.py`

**Interfaces:**
- Produces: `compute_interval(estimated_seconds: float | None, clip_seconds: int, clip_fps: int, default_interval: int, min_interval: int, max_interval: int) -> int`
- Produces: `parse_status(data: dict) -> dict` now also returns keys `gcode_name: str | None` and `estimated_seconds: float | None`.
- Produces: new `DEFAULT_CONFIG` keys (consumed by Tasks 5-6): `stream_id, clip_seconds, clip_fps, default_interval_seconds, min_interval_seconds, max_interval_seconds, timestamp_overlay, logo_overlay, deflicker, quality, ha_sensors` (legacy `profile_id`, `fps`, `format` removed).

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_prusalink.py`:

```python
# --- compute_interval -------------------------------------------------------

def test_interval_scales_with_estimate():
    # 10h print, 20s x 25fps = 500 frames -> 72s
    assert pl.compute_interval(36000, 20, 25, 10, 2, 120) == 72
    # 25min print -> 3s
    assert pl.compute_interval(1500, 20, 25, 10, 2, 120) == 3

def test_interval_clamps_to_bounds():
    assert pl.compute_interval(60, 20, 25, 10, 2, 120) == 2      # tiny print -> min
    assert pl.compute_interval(1_000_000, 20, 25, 10, 2, 120) == 120  # huge -> max

def test_interval_missing_or_bogus_estimate_uses_default():
    for est in (None, 0, -5):
        assert pl.compute_interval(est, 20, 25, 10, 2, 120) == 10

def test_interval_default_is_also_clamped():
    assert pl.compute_interval(None, 20, 25, 300, 2, 120) == 120


# --- parse_status: job metadata ---------------------------------------------

def test_parse_status_extracts_gcode_name_and_estimate():
    got = pl.parse_status({
        "printer": {"state": "PRINTING"},
        "job": {
            "id": 7, "progress": 12.5,
            "time_printing": 300, "time_remaining": 3300,
            "file": {"name": "benchy~1.gco", "display_name": "benchy.gcode"},
        },
    })
    assert got["gcode_name"] == "benchy.gcode"
    assert got["estimated_seconds"] == 3600.0

def test_parse_status_falls_back_to_file_name():
    got = pl.parse_status({"printer": {}, "job": {"file": {"name": "x.gco"}}})
    assert got["gcode_name"] == "x.gco"

def test_parse_status_no_estimate_when_remaining_missing_or_bogus():
    assert pl.parse_status({"job": {"time_printing": 300}})["estimated_seconds"] is None
    assert pl.parse_status({"job": {"time_remaining": -1}})["estimated_seconds"] is None
    assert pl.parse_status({})["estimated_seconds"] is None
    assert pl.parse_status({})["gcode_name"] is None
```

- [ ] **Step 2: Run to verify failure** — `tests/test_prusalink.py`. Expected: FAIL (`AttributeError: ... 'compute_interval'`, KeyError on new keys).

- [ ] **Step 3: Implement** in `backend/app/services/prusalink.py`:

Replace `DEFAULT_CONFIG` (lines 29-37):

```python
DEFAULT_CONFIG = {
    "stream_id": None,
    "poll_interval_seconds": 10,
    "generate_on_finish": True,
    "generate_on_cancel": False,
    "enabled": True,
    "clip_seconds": 20,
    "clip_fps": 25,
    "default_interval_seconds": 10,
    "min_interval_seconds": 2,
    "max_interval_seconds": 120,
    "timestamp_overlay": True,
    "logo_overlay": False,
    "deflicker": "medium",
    "quality": 90,
    "ha_sensors": None,
}
```

Replace `parse_status` (lines 102-110):

```python
def parse_status(data: dict) -> dict:
    """Extract the bits we care about from a PrusaLink /api/v1/status response."""
    printer = (data or {}).get("printer") or {}
    job = (data or {}).get("job") or {}
    file_info = job.get("file") or {}
    remaining = job.get("time_remaining")
    printing = job.get("time_printing")
    estimated = None
    if isinstance(remaining, (int, float)) and remaining > 0:
        estimated = float(remaining)
        if isinstance(printing, (int, float)) and printing > 0:
            estimated += float(printing)
    return {
        "state": printer.get("state"),
        "job_id": job.get("id"),
        "progress": job.get("progress"),
        "gcode_name": file_info.get("display_name") or file_info.get("name"),
        "estimated_seconds": estimated,
    }
```

Add after `decide_transition`:

```python
def compute_interval(
    estimated_seconds: float | None,
    clip_seconds: int,
    clip_fps: int,
    default_interval: int,
    min_interval: int,
    max_interval: int,
) -> int:
    """Capture interval so a print of the estimated length yields roughly
    clip_seconds x clip_fps frames. Missing/bogus estimate -> default. Always
    clamped to [min_interval, max_interval]."""
    if not estimated_seconds or estimated_seconds <= 0:
        interval = default_interval
    else:
        target_frames = max(1, clip_seconds * clip_fps)
        interval = round(estimated_seconds / target_frames)
    return int(max(min_interval, min(max_interval, interval)))
```

- [ ] **Step 4: Run to verify pass** — `tests/test_prusalink.py`. Expected: PASS. (Older reconcile-free tests in this file only touch `normalize_state`/`decide_transition` and must still pass.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prusalink.py backend/tests/test_prusalink.py
git commit -m "feat(prusalink): per-print interval computation + job metadata parsing"
```

---

### Task 3: Managed profile helper

**Files:**
- Modify: `backend/app/services/prusalink.py`
- Test: `backend/tests/test_prusalink.py`

**Interfaces:**
- Produces: `MANAGED_PROFILE_NAME = "3D Print (auto)"` and `ensure_managed_profile(db, cfg: dict) -> Profile | None` — finds or creates the single `managed_by='prusalink'` profile, re-points it to `cfg["stream_id"]`, and writes through capture/render settings from cfg. Returns None when `cfg["stream_id"]` is falsy.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_prusalink.py`:

```python
# --- ensure_managed_profile --------------------------------------------------

from app.models import Profile, Stream


def _stream(db):
    s = Stream(name="printer-cam", url="rtsp://x", type="rtsp")
    db.add(s)
    db.commit()
    return s


def _cfg(**over):
    cfg = pl.DEFAULT_CONFIG.copy()
    cfg.update(over)
    return cfg


def test_ensure_managed_profile_creates_once_and_repoints(db):
    s1, s2 = _stream(db), _stream(db)
    p = pl.ensure_managed_profile(db, _cfg(stream_id=s1.id, quality=85, clip_seconds=30, clip_fps=30))
    assert p.managed_by == "prusalink"
    assert p.name == pl.MANAGED_PROFILE_NAME
    assert p.enabled is False
    assert p.quality == 85
    assert p.fps_mode == "target_duration"
    assert p.render_target_seconds == 30
    assert p.render_fps == 30
    # second call: same row, re-pointed to the other stream
    p2 = pl.ensure_managed_profile(db, _cfg(stream_id=s2.id))
    assert p2.id == p.id
    assert p2.stream_id == s2.id
    assert db.query(Profile).filter(Profile.managed_by == "prusalink").count() == 1


def test_ensure_managed_profile_none_without_stream(db):
    assert pl.ensure_managed_profile(db, _cfg(stream_id=None)) is None
```

(Adjust `_stream` to the same constructor pattern used in Task 1.)

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, `AttributeError: ensure_managed_profile`.

- [ ] **Step 3: Implement** — add to `backend/app/services/prusalink.py` (after `get_config`):

```python
MANAGED_PROFILE_NAME = "3D Print (auto)"


def ensure_managed_profile(db, cfg: dict):
    """Find-or-create the integration-owned capture profile and sync it to the
    current settings. There is at most one; it is hidden from the profiles UI
    and its interval is rewritten per print."""
    stream_id = cfg.get("stream_id")
    if not stream_id:
        return None
    profile = db.query(Profile).filter(Profile.managed_by == "prusalink").first()
    if profile is None:
        profile = Profile(
            stream_id=stream_id,
            name=MANAGED_PROFILE_NAME,
            managed_by="prusalink",
            enabled=False,
            interval_seconds=cfg.get("default_interval_seconds", 10),
        )
        db.add(profile)
    profile.stream_id = stream_id
    profile.quality = cfg.get("quality", 90)
    profile.ha_sensors = cfg.get("ha_sensors") or None
    profile.fps_mode = "target_duration"
    profile.render_target_seconds = cfg.get("clip_seconds", 20)
    profile.render_fps = cfg.get("clip_fps", 25)
    db.commit()
    return profile
```

- [ ] **Step 4: Run to verify pass** — `tests/test_prusalink.py`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prusalink.py backend/tests/test_prusalink.py
git commit -m "feat(prusalink): integration-owned managed capture profile"
```

---

### Task 4: Timelapse name + print-job linking through the render pipeline

**Files:**
- Modify: `backend/app/services/timelapse.py` (`generate_timelapse` params + record creation)
- Modify: `backend/app/schemas.py` (`TimelapseRead.name`)
- Test: `backend/tests/test_timelapses.py` (or `test_print_jobs.py` if `test_timelapses.py` is API-level only — put it where a plain `db` fixture test fits; `test_print_jobs.py` is fine)

**Interfaces:**
- Consumes: `PrintJob` (Task 1).
- Produces: `generate_timelapse(..., name: str | None = None, print_job_id: int | None = None)` — stores `name` on the `Timelapse` row; after insert, sets `print_jobs.timelapse_id = <new id>` when `print_job_id` given. `TimelapseRead` gains `name: str | None = None`.

- [ ] **Step 1: Write failing test** — the ffmpeg path is heavy; test the record-linking helper instead. First extract it. Append to `backend/tests/test_print_jobs.py`:

```python
def test_link_print_job_sets_timelapse_id(db):
    from datetime import UTC, datetime
    from app.services.timelapse import _link_print_job
    s = _mk_stream(db)
    p = Profile(stream_id=s.id, name="x")
    db.add(p)
    db.commit()
    tl = Timelapse(profile_id=p.id, file_path="x.mp4")
    pj = PrintJob(stream_id=s.id, status="finished", started_at=datetime.now(UTC))
    db.add_all([tl, pj])
    db.commit()
    _link_print_job(db, pj.id, tl.id)
    assert db.get(PrintJob, pj.id).timelapse_id == tl.id
    # unknown print_job_id is a no-op, not an error
    _link_print_job(db, 99999, tl.id)
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, ImportError `_link_print_job`.

- [ ] **Step 3: Implement** in `backend/app/services/timelapse.py`:

Add near the other module-level helpers:

```python
def _link_print_job(db, print_job_id: int, timelapse_id: int) -> None:
    """Point a print_jobs row at its generated timelapse (no-op if gone)."""
    from app.models import PrintJob
    pj = db.get(PrintJob, print_job_id)
    if pj:
        pj.timelapse_id = timelapse_id
        db.commit()
```

In `generate_timelapse`'s signature (line ~440), add after `quality_preset: str = "medium",`:

```python
    name: str | None = None,
    print_job_id: int | None = None,
```

In the `Timelapse(...)` record creation (line ~891), add `name=name,` after `thumbnail_path=thumb_path,`.

After the `db.add(timelapse)` block commits and the new id is available (the function already commits and later returns the id — find the `db.add(timelapse)` / commit and add immediately after the commit):

```python
        if print_job_id is not None:
            _link_print_job(db, print_job_id, timelapse.id)
```

In `backend/app/schemas.py`, `TimelapseRead`: add `name: str | None = None` after `profile_id: int`.

- [ ] **Step 4: Run to verify pass** — `tests/test_print_jobs.py tests/test_timelapses.py tests/test_timelapse_ffmpeg.py`. Expected: PASS (existing generate tests unaffected — new params default to None).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/timelapse.py backend/app/schemas.py backend/tests/test_print_jobs.py
git commit -m "feat(timelapse): optional name + print-job back-link on generated records"
```

---

### Task 5: Reconcile rewrite — print_jobs lifecycle, dynamic interval, overlay-aware enqueue

**Files:**
- Modify: `backend/app/services/prusalink.py` (`_reconcile`, `poll_printer`; delete `_profile_render_config`, `_parse_started_at`, `_DT_FMT` usage for print state)
- Test: `backend/tests/test_prusalink.py`

**Interfaces:**
- Consumes: `compute_interval`, `ensure_managed_profile`, `parse_status` dict (Tasks 2-3), `PrintJob` (Task 1), `generate_timelapse` kwargs `name`/`print_job_id` (Task 4, passed via `enqueue_generation`).
- Produces: `_reconcile(db, cfg, status: dict) -> PrintDecision` (signature change: takes the parsed status dict, not just `raw_state`). `poll_printer` gates on `cfg["stream_id"]` and passes the full status.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_prusalink.py`:

```python
# --- _reconcile lifecycle -----------------------------------------------------

import pytest
from app.models import PrintJob


@pytest.fixture
def fakes(monkeypatch):
    """Stub the scheduler + generation queue; capture calls."""
    calls = {"add": [], "remove": [], "resched": [], "enqueue": [], "events": []}
    monkeypatch.setattr(pl.scheduler, "add_capture_job", lambda p: calls["add"].append(p.id))
    monkeypatch.setattr(pl.scheduler, "remove_capture_job", lambda pid: calls["remove"].append(pid))
    monkeypatch.setattr(pl.scheduler, "reschedule_capture_job", lambda p: calls["resched"].append((p.id, p.interval_seconds)))

    async def _enqueue(**kw):
        calls["enqueue"].append(kw)
        return {"generation_id": "t", "position": 1}

    async def _emit(*a, **kw):
        calls["events"].append(a)

    monkeypatch.setattr(pl.generation_queue, "enqueue_generation", _enqueue)
    monkeypatch.setattr(pl.events, "emit", _emit)
    return calls


def _status(state, *, job_id=1, name="benchy.gcode", est=None):
    return {"state": state, "job_id": job_id, "progress": 0,
            "gcode_name": name,
            "estimated_seconds": est}


async def _run(db, cfg, status):
    return await pl._reconcile(db, cfg, status)


@pytest.mark.anyio
async def test_start_creates_print_job_with_computed_interval(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=36000))
    pj = db.query(PrintJob).one()
    assert pj.status == "printing"
    assert pj.gcode_name == "benchy.gcode"
    assert pj.interval_seconds == 72  # 36000 / (20*25)
    profile = db.query(Profile).filter(Profile.managed_by == "prusalink").one()
    assert profile.enabled is True
    assert profile.interval_seconds == 72
    assert fakes["add"] == [profile.id]


@pytest.mark.anyio
async def test_start_without_estimate_uses_default_then_recomputes_once(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=None))
    pj = db.query(PrintJob).one()
    assert pj.interval_seconds == 10  # default
    assert pj.estimated_seconds is None
    # estimate appears on a later poll -> recompute exactly once
    await _run(db, cfg, _status("PRINTING", est=36000))
    db.refresh(pj)
    assert pj.interval_seconds == 72
    assert fakes["resched"] == [(db.query(Profile).one().id, 72)]
    # further polls with a different estimate do NOT recompute again
    await _run(db, cfg, _status("PRINTING", est=50000))
    db.refresh(pj)
    assert pj.interval_seconds == 72


@pytest.mark.anyio
async def test_finish_closes_job_and_enqueues_named_render(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=1500))
    await _run(db, cfg, _status("FINISHED"))
    pj = db.query(PrintJob).one()
    assert pj.status == "finished"
    assert pj.finished_at is not None
    profile = db.query(Profile).one()
    assert profile.enabled is False
    assert fakes["remove"] == [profile.id]
    (kw,) = fakes["enqueue"]
    assert kw["name"] == "benchy.gcode"
    assert kw["print_job_id"] == pj.id
    assert kw["fps_mode"] == "target_duration"
    assert kw["render_target_seconds"] == 20
    assert kw["timestamp_overlay"] is True
    assert kw["logo_overlay"] is False
    assert kw["deflicker"] == "medium"
    assert kw["period_start"] == pj.started_at


@pytest.mark.anyio
async def test_cancel_respects_generate_on_cancel(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id, generate_on_cancel=False)
    await _run(db, cfg, _status("PRINTING", est=1500))
    await _run(db, cfg, _status("IDLE"))
    pj = db.query(PrintJob).one()
    assert pj.status == "cancelled"
    assert fakes["enqueue"] == []


@pytest.mark.anyio
async def test_active_state_survives_restart_via_open_row(db, fakes):
    """Active = open print_jobs row; no in-memory/settings flag involved."""
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=1500))
    # simulate restart: nothing reset, next poll sees FINISHED
    await _run(db, cfg, _status("FINISHED"))
    assert db.query(PrintJob).one().status == "finished"
```

Check `backend/tests/conftest.py` / existing async tests for the async plugin in use: if the suite uses `pytest-asyncio`, mark with `@pytest.mark.asyncio` instead of `anyio` (`grep -rn "asyncio\|anyio" backend/tests/*.py | head` and copy the existing convention; `test_generation_queue.py` likely has async tests).

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (signature mismatch: `_reconcile` takes `raw_state`, no PrintJob handling).

- [ ] **Step 3: Implement** — in `backend/app/services/prusalink.py` replace `_profile_render_config`, `_parse_started_at`, `_reconcile`, and `poll_printer` with:

```python
def _open_print_job(db):
    return (
        db.query(PrintJob)
        .filter(PrintJob.status == "printing")
        .order_by(PrintJob.id.desc())
        .first()
    )


def _apply_interval(db, profile, pj, interval: int, *, reschedule: bool) -> None:
    pj.interval_seconds = interval
    profile.interval_seconds = interval
    db.commit()
    if reschedule:
        scheduler.reschedule_capture_job(profile)


async def _reconcile(db, cfg: dict, status: dict) -> PrintDecision:
    """Apply the side effects implied by a single polled status."""
    pj = _open_print_job(db)
    state = normalize_state(status.get("state"))
    d = decide_transition(pj is not None, state, cfg.get("generate_on_cancel", False))

    profile = None
    if d.start_capture or pj is not None:
        profile = ensure_managed_profile(db, cfg)

    if d.start_capture and profile:
        interval = compute_interval(
            status.get("estimated_seconds"),
            cfg["clip_seconds"], cfg["clip_fps"],
            cfg["default_interval_seconds"],
            cfg["min_interval_seconds"], cfg["max_interval_seconds"],
        )
        pj = PrintJob(
            prusalink_job_id=status.get("job_id"),
            gcode_name=status.get("gcode_name") or "",
            stream_id=profile.stream_id,
            status="printing",
            started_at=datetime.now(UTC),
            estimated_seconds=status.get("estimated_seconds"),
            interval_seconds=interval,
        )
        db.add(pj)
        profile.enabled = True
        profile.interval_seconds = interval
        db.commit()
        scheduler.add_capture_job(profile)

    elif pj and state == "printing" and profile:
        # Recompute once: the print started before PrusaLink knew its length.
        if pj.estimated_seconds is None and status.get("estimated_seconds"):
            pj.estimated_seconds = status["estimated_seconds"]
            interval = compute_interval(
                pj.estimated_seconds,
                cfg["clip_seconds"], cfg["clip_fps"],
                cfg["default_interval_seconds"],
                cfg["min_interval_seconds"], cfg["max_interval_seconds"],
            )
            _apply_interval(db, profile, pj, interval, reschedule=True)
        if not pj.gcode_name and status.get("gcode_name"):
            pj.gcode_name = status["gcode_name"]
            db.commit()

    if d.stop_capture and pj:
        if profile:
            scheduler.remove_capture_job(profile.id)
            profile.enabled = False
        pj.status = "finished" if d.event == "print_finished" else "cancelled"
        pj.finished_at = datetime.now(UTC)
        db.commit()

    should_generate = d.generate
    if d.event == "print_finished" and not cfg.get("generate_on_finish", True):
        should_generate = False
    if should_generate and pj and profile:
        await generation_queue.enqueue_generation(
            profile_id=profile.id,
            period_type="custom",
            period_start=pj.started_at,
            period_end=datetime.now(UTC),
            fps_mode="target_duration",
            fps=cfg["clip_fps"],
            render_target_seconds=cfg["clip_seconds"],
            format="mp4",
            timestamp_overlay=cfg.get("timestamp_overlay", True),
            logo_overlay=cfg.get("logo_overlay", False),
            deflicker=cfg.get("deflicker", "medium"),
            ha_overlay=bool(profile.ha_sensors),
            name=pj.gcode_name or None,
            print_job_id=pj.id,
        )

    if d.event:
        title, level = _EVENT_META.get(d.event, (d.event, "info"))
        name = (pj.gcode_name if pj and pj.gcode_name else None) or "print"
        await events.emit(d.event, title, f"{title}: {name}", level=level)

    return d


async def poll_printer() -> None:
    """Scheduled job: poll PrusaLink and reconcile the print lifecycle."""
    db = SessionLocal()
    try:
        cfg = get_config(db)
        if not cfg or not cfg.get("enabled", True) or not cfg.get("stream_id"):
            return
        status = await get_status(cfg["base_url"], cfg["username"], cfg["password"])
        if not status or not status.get("state"):
            return
        await _reconcile(db, cfg, status)
    except Exception:
        logger.exception("PrusaLink poll failed")
    finally:
        db.rollback()
        db.close()
```

Update the imports line: `from app.models import PrintJob, Profile, Setting` and remove now-unused `timedelta` / `_DT_FMT` if nothing else references them (grep first). Keep `_get_setting`/`_set_setting` only if still used by `get_config` (`_get_setting` is — keep it; delete `_set_setting` if now unused).

Restart recovery note (verify, no code expected): `scheduler.restore_jobs` (backend/app/services/scheduler.py:86) re-adds capture jobs for `enabled` profiles at boot — a managed profile mid-print is `enabled=True`, so capture resumes after restart, and the open `print_jobs` row keeps reconcile state. No extra code needed; confirm by reading `restore_jobs`.

- [ ] **Step 4: Run to verify pass** — `tests/test_prusalink.py`. Expected: PASS, including the pre-existing pure-function tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prusalink.py backend/tests/test_prusalink.py
git commit -m "feat(prusalink): per-print lifecycle via print_jobs + dynamic interval reconcile"
```

---

### Task 6: Settings API — new schema, blob fields, managed-profile write-through

**Files:**
- Modify: `backend/app/schemas.py` (`PrusaLinkConfig`, `PrusaLinkRead`)
- Modify: `backend/app/routers/settings.py` (`_PRUSALINK_BLOB_FIELDS`, PUT handler)
- Modify: `backend/app/main.py:66` (startup gate)
- Test: `backend/tests/test_settings_router.py`

**Interfaces:**
- Consumes: `ensure_managed_profile` (Task 3), new `DEFAULT_CONFIG` keys (Task 2).
- Produces: `PrusaLinkConfig`/`PrusaLinkRead` with fields `base_url, username, password (write-only), stream_id: int | None, poll_interval_seconds, generate_on_finish, generate_on_cancel, enabled, clip_seconds, clip_fps, default_interval_seconds, min_interval_seconds, max_interval_seconds, timestamp_overlay, logo_overlay, deflicker, quality, ha_sensors` (+ read-only `configured`, `connected`). Frontend (Task 8) consumes exactly these names.

- [ ] **Step 1: Write failing test** — append to `backend/tests/test_settings_router.py`:

```python
def test_prusalink_roundtrip_and_managed_profile(client, db):
    from app.models import Profile, Stream
    s = Stream(name="printer-cam", url="rtsp://x", type="rtsp")
    db.add(s)
    db.commit()
    payload = {
        "base_url": "http://prusa.local", "username": "maker", "password": "pw",
        "stream_id": s.id, "poll_interval_seconds": 10,
        "generate_on_finish": True, "generate_on_cancel": False, "enabled": False,
        "clip_seconds": 30, "clip_fps": 30, "default_interval_seconds": 5,
        "min_interval_seconds": 2, "max_interval_seconds": 60,
        "timestamp_overlay": False, "logo_overlay": True, "deflicker": "high",
        "quality": 80, "ha_sensors": None,
    }
    resp = client.put("/api/settings/prusalink", json=payload)
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/prusalink").json()
    assert got["stream_id"] == s.id
    assert got["clip_seconds"] == 30
    assert got["logo_overlay"] is True
    assert "password" not in got
    assert "profile_id" not in got
    # managed profile created + synced
    mp = db.query(Profile).filter(Profile.managed_by == "prusalink").one()
    assert mp.stream_id == s.id
    assert mp.quality == 80
    assert mp.render_target_seconds == 30
    assert mp.render_fps == 30
    assert mp.fps_mode == "target_duration"
```

(Adjust the `Stream(...)` constructor to the pattern from Task 1. `enabled: False` keeps the PUT from registering a real poll job in the test app. GET runs a live-probe branch only when `configured` and config present — it is: probe is wrapped by `health_status.reachable` cache against an unreachable host; if this makes the test flaky/slow, monkeypatch `app.services.health_status.reachable` to an async lambda returning False.)

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, 422 (unknown/missing fields on `PrusaLinkConfig`).

- [ ] **Step 3: Implement**

`backend/app/schemas.py` — replace `PrusaLinkConfig`/`PrusaLinkRead` (lines 67-91):

```python
class PrusaLinkConfig(BaseModel):
    base_url: str
    username: str = "maker"
    password: str | None = None  # write-only; omitted on read
    stream_id: int | None = None
    poll_interval_seconds: int = Field(default=10, ge=5)
    generate_on_finish: bool = True
    generate_on_cancel: bool = False
    enabled: bool = True
    clip_seconds: int = Field(default=20, ge=1, le=300)
    clip_fps: int = Field(default=25, ge=1, le=120)
    default_interval_seconds: int = Field(default=10, ge=1)
    min_interval_seconds: int = Field(default=2, ge=1)
    max_interval_seconds: int = Field(default=120, ge=1)
    timestamp_overlay: bool = True
    logo_overlay: bool = False
    deflicker: str = "medium"
    quality: int = Field(default=90, ge=1, le=100)
    ha_sensors: str | None = None  # JSON string: [{entity_id,label,unit,icon}]


class PrusaLinkRead(BaseModel):
    base_url: str
    username: str
    stream_id: int | None
    poll_interval_seconds: int
    generate_on_finish: bool
    generate_on_cancel: bool
    enabled: bool
    clip_seconds: int
    clip_fps: int
    default_interval_seconds: int
    min_interval_seconds: int
    max_interval_seconds: int
    timestamp_overlay: bool
    logo_overlay: bool
    deflicker: str
    quality: int
    ha_sensors: str | None
    configured: bool  # credentials present (drives the password placeholder)
    connected: bool  # live reachability probe (cached); drives the status badge
```

`backend/app/routers/settings.py` — replace `_PRUSALINK_BLOB_FIELDS` (line 324):

```python
_PRUSALINK_BLOB_FIELDS = (
    "stream_id", "poll_interval_seconds", "generate_on_finish", "generate_on_cancel",
    "enabled", "clip_seconds", "clip_fps", "default_interval_seconds",
    "min_interval_seconds", "max_interval_seconds",
    "timestamp_overlay", "logo_overlay", "deflicker", "quality", "ha_sensors",
)
```

In `update_prusalink_settings` (line 367), after `db.commit()` add the managed-profile sync, and change the poll-job gate to `stream_id`:

```python
    from app.services import health_status, prusalink
    from app.services.scheduler import add_prusalink_poll_job, remove_prusalink_poll_job

    cfg = prusalink.get_config(db)
    if cfg:
        prusalink.ensure_managed_profile(db, cfg)
    if data.enabled and url and data.stream_id:
        add_prusalink_poll_job(data.poll_interval_seconds)
    else:
        remove_prusalink_poll_job()
```

`backend/app/main.py` line 66 — change gate:

```python
    if prusalink_cfg and prusalink_cfg.get("enabled", True) and prusalink_cfg.get("stream_id"):
```

- [ ] **Step 4: Run to verify pass** — `tests/test_settings_router.py tests/test_prusalink.py`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/settings.py backend/app/main.py backend/tests/test_settings_router.py
git commit -m "feat(prusalink): stream-bound settings API with clip + overlay config"
```

---

### Task 7: Print-jobs read API + managed-profile guards

**Files:**
- Create: `backend/app/routers/print_jobs.py`
- Modify: `backend/app/main.py` (register router)
- Modify: `backend/app/schemas.py` (add `PrintJobRead`; add `managed_by` to `ProfileRead`)
- Modify: `backend/app/routers/profiles.py` (hide managed from lists; block update/delete/enable/disable)
- Test: `backend/tests/test_print_jobs.py`, `backend/tests/test_profiles.py`

**Interfaces:**
- Consumes: `PrintJob` model.
- Produces: `GET /api/print-jobs` → `list[PrintJobRead]`, newest first, fields `id, gcode_name, stream_id, status, started_at, finished_at, estimated_seconds, interval_seconds, timelapse_id`. `ProfileRead.managed_by: str | None = None`. Managed profiles: excluded from `GET /api/profiles` and `GET /api/streams/{id}/profiles`; `PUT/DELETE/enable/disable` on them → 409.

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_print_jobs.py`:

```python
def test_list_print_jobs_newest_first(client, db):
    from datetime import UTC, datetime
    s = _mk_stream(db)
    for n in ("a.gcode", "b.gcode"):
        db.add(PrintJob(stream_id=s.id, gcode_name=n, status="finished",
                        started_at=datetime.now(UTC)))
    db.commit()
    got = client.get("/api/print-jobs").json()
    assert [j["gcode_name"] for j in got] == ["b.gcode", "a.gcode"]
    assert {"id", "status", "started_at", "timelapse_id"} <= set(got[0])
```

Append to `backend/tests/test_profiles.py` (mirror its existing stream/profile setup helpers):

```python
def test_managed_profiles_hidden_and_guarded(client, db):
    from app.models import Profile, Stream
    s = Stream(name="printer-cam", url="rtsp://x", type="rtsp")
    db.add(s)
    db.commit()
    mp = Profile(stream_id=s.id, name="3D Print (auto)", managed_by="prusalink", enabled=False)
    db.add(mp)
    db.commit()
    assert all(p["id"] != mp.id for p in client.get("/api/profiles").json())
    assert all(p["id"] != mp.id for p in client.get(f"/api/streams/{s.id}/profiles").json())
    assert client.put(f"/api/profiles/{mp.id}", json={"name": "hijack"}).status_code == 409
    assert client.delete(f"/api/profiles/{mp.id}").status_code == 409
    assert client.post(f"/api/profiles/{mp.id}/disable").status_code == 409
```

(Adjust the enable/disable route method/path to what `backend/app/routers/profiles.py:120-134` actually defines — check whether they are POST or PUT before writing the assertion.)

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (404 on /api/print-jobs; managed profile present in lists; 200 on guarded calls).

- [ ] **Step 3: Implement**

`backend/app/schemas.py`:

```python
class PrintJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gcode_name: str
    stream_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    estimated_seconds: float | None
    interval_seconds: int | None
    timelapse_id: int | None
```

And in `ProfileRead`, after `source_template_id`: `managed_by: str | None = None`.

Create `backend/app/routers/print_jobs.py`:

```python
"""Read API for PrusaLink print history."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PrintJob
from app.schemas import PrintJobRead

router = APIRouter(prefix="/api/print-jobs", tags=["print-jobs"])


@router.get("", response_model=list[PrintJobRead])
def list_print_jobs(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(PrintJob)
        .order_by(PrintJob.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
```

`backend/app/main.py`: import `print_jobs` alongside the other routers and add `app.include_router(print_jobs.router)` after the `timelapses` line.

`backend/app/routers/profiles.py`:
- In `list_all_profiles` (line 22) and `list_profiles` (line 30): add `.filter(Profile.managed_by.is_(None))` to the queries.
- Add a guard helper and call it at the top of `update_profile`, `delete_profile`, `enable_profile`, `disable_profile` right after the profile is fetched/404-checked:

```python
def _reject_managed(profile: Profile) -> None:
    if profile.managed_by:
        raise HTTPException(409, "Profile is managed by an integration; edit it in Settings")
```

- [ ] **Step 4: Run to verify pass** — `tests/test_print_jobs.py tests/test_profiles.py`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/print_jobs.py backend/app/routers/profiles.py backend/app/main.py backend/app/schemas.py backend/tests/test_print_jobs.py backend/tests/test_profiles.py
git commit -m "feat(api): print-jobs history endpoint; hide + guard managed profiles"
```

---

### Task 8: Frontend — reworked 3D Printing settings section

**Files:**
- Modify: `frontend/src/lib/types.ts` (`PrusaLinkConfig`; add `PrintJob`; add `name` to `Timelapse`)
- Modify: `frontend/src/lib/api.ts` (add `getPrintJobs`)
- Modify: `frontend/src/routes/settings/+page.svelte` (section rework)

**Interfaces:**
- Consumes: API fields from Task 6/7 exactly as named there.
- Produces: `api.getPrintJobs(): Promise<PrintJob[]>`; `PrusaLinkConfig` TS type matching `PrusaLinkRead`.

- [ ] **Step 1: Update types** — in `frontend/src/lib/types.ts` replace the `PrusaLinkConfig` interface (line ~458):

```ts
export interface PrusaLinkConfig {
	base_url: string;
	username: string;
	password?: string;
	stream_id: number | null;
	poll_interval_seconds: number;
	generate_on_finish: boolean;
	generate_on_cancel: boolean;
	enabled: boolean;
	clip_seconds: number;
	clip_fps: number;
	default_interval_seconds: number;
	min_interval_seconds: number;
	max_interval_seconds: number;
	timestamp_overlay: boolean;
	logo_overlay: boolean;
	deflicker: string;
	quality: number;
	ha_sensors: string | null;
	configured: boolean;
	connected: boolean;
}

export interface PrintJob {
	id: number;
	gcode_name: string;
	stream_id: number;
	status: 'printing' | 'finished' | 'cancelled';
	started_at: string;
	finished_at: string | null;
	estimated_seconds: number | null;
	interval_seconds: number | null;
	timelapse_id: number | null;
}
```

Add `name: string | null;` to the existing `Timelapse` interface, and in `frontend/src/lib/api.ts` add (near the timelapse methods) `getPrintJobs: () => request<PrintJob[]>('/print-jobs'),` plus the `PrintJob` type import.

- [ ] **Step 2: Rework the settings section script** — in `frontend/src/routes/settings/+page.svelte`:

Replace `loadPrusaProfiles` (lines 129-140) with a camera loader (and rename the `prusaProfiles` state variable accordingly — find its `$state` declaration near the top):

```ts
let prusaStreams = $state<{ id: number; name: string }[]>([]);
let haEntities = $state<HAEntity[]>([]);

async function loadPrusaStreams() {
	try {
		const streams = await api.getStreams();
		prusaStreams = streams.map((s) => ({ id: s.id, name: s.name }));
	} catch {
		prusaStreams = [];
	}
	// Sensor list for the overlay picker; absent/unconfigured HA is fine.
	try {
		haEntities = await api.getHAEntities();
	} catch {
		haEntities = [];
	}
}
```

Update the `$effect` call site (line 126) from `loadPrusaProfiles()` to `loadPrusaStreams()`.

Add ha_sensors helpers (the field is a JSON string of `{entity_id,label,unit,icon}` — same encoding profiles use):

```ts
function prusaSensorIds(): string[] {
	try {
		return (JSON.parse(prusaConfig.ha_sensors ?? '[]') as { entity_id: string }[]).map((s) => s.entity_id);
	} catch {
		return [];
	}
}

function togglePrusaSensor(e: HAEntity) {
	const ids = prusaSensorIds();
	let list: { entity_id: string; label: string; unit: string | null; icon: string | null }[];
	try {
		list = JSON.parse(prusaConfig.ha_sensors ?? '[]');
	} catch {
		list = [];
	}
	if (ids.includes(e.entity_id)) {
		list = list.filter((s) => s.entity_id !== e.entity_id);
	} else {
		list = [...list, { entity_id: e.entity_id, label: e.label ?? e.entity_id, unit: e.unit ?? null, icon: e.icon ?? null }];
	}
	prusaConfig.ha_sensors = list.length ? JSON.stringify(list) : null;
}
```

(Check the `HAEntity` type in `frontend/src/lib/types.ts` for the actual property names — `label`/`unit`/`icon` above must match it; also check how the stream profile form at `frontend/src/routes/streams/[id]/+page.svelte` serializes `ha_sensors` and use the identical object shape.)

- [ ] **Step 3: Rework the section markup** (lines 751-853). Replace the description paragraph, the "Capture profile" select, and the fps/format grid with:

Description (line 763-765):

```svelte
<p class="mb-4 text-sm text-gray-400">
	Poll a Prusa printer's local PrusaLink API and capture a timelapse for each print. Pick the camera pointed at the printer — capture interval is computed per print from the printer's time estimate, so short and overnight prints both render to the clip length below.
</p>
```

Camera + poll interval grid (replaces the profile/poll grid at lines 786-802):

```svelte
<div class="mb-4 grid grid-cols-2 gap-4">
	<div>
		<label for="prusa-stream" class="mb-1 block text-sm text-gray-400">Camera</label>
		<select id="prusa-stream" bind:value={prusaConfig.stream_id}
			class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
			<option value={null}>— Select a camera —</option>
			{#each prusaStreams as s}
				<option value={s.id}>{s.name}</option>
			{/each}
		</select>
	</div>
	<div>
		<label for="prusa-poll" class="mb-1 block text-sm text-gray-400">Poll interval (seconds)</label>
		<input id="prusa-poll" type="number" min="5" bind:value={prusaConfig.poll_interval_seconds}
			class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
	</div>
</div>
```

Clip settings grid (replaces the fps/format grid at lines 804-819):

```svelte
<div class="mb-4 grid grid-cols-3 gap-4">
	<div>
		<label for="prusa-clip-len" class="mb-1 block text-sm text-gray-400">Clip length (seconds)</label>
		<input id="prusa-clip-len" type="number" min="1" max="300" bind:value={prusaConfig.clip_seconds}
			class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
	</div>
	<div>
		<label for="prusa-clip-fps" class="mb-1 block text-sm text-gray-400">Clip FPS</label>
		<input id="prusa-clip-fps" type="number" min="1" max="120" bind:value={prusaConfig.clip_fps}
			class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
	</div>
	<div>
		<label for="prusa-default-int" class="mb-1 block text-sm text-gray-400">Fallback interval (s)</label>
		<input id="prusa-default-int" type="number" min="1" bind:value={prusaConfig.default_interval_seconds}
			class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
	</div>
</div>

<details class="mb-4 rounded-lg border border-gray-800 p-3">
	<summary class="cursor-pointer text-sm text-gray-400">Advanced: interval clamp</summary>
	<div class="mt-3 grid grid-cols-2 gap-4">
		<div>
			<label for="prusa-min-int" class="mb-1 block text-sm text-gray-400">Min interval (s)</label>
			<input id="prusa-min-int" type="number" min="1" bind:value={prusaConfig.min_interval_seconds}
				class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
		</div>
		<div>
			<label for="prusa-max-int" class="mb-1 block text-sm text-gray-400">Max interval (s)</label>
			<input id="prusa-max-int" type="number" min="1" bind:value={prusaConfig.max_interval_seconds}
				class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
		</div>
	</div>
</details>

<details class="mb-4 rounded-lg border border-gray-800 p-3">
	<summary class="cursor-pointer text-sm text-gray-400">Overlays &amp; render</summary>
	<div class="mt-3 space-y-3">
		<div class="grid grid-cols-2 gap-4">
			<div>
				<label for="prusa-quality" class="mb-1 block text-sm text-gray-400">Capture quality ({prusaConfig.quality})</label>
				<input id="prusa-quality" type="range" min="1" max="100" bind:value={prusaConfig.quality} class="w-full" />
			</div>
			<div>
				<label for="prusa-deflicker" class="mb-1 block text-sm text-gray-400">Deflicker</label>
				<select id="prusa-deflicker" bind:value={prusaConfig.deflicker}
					class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
					<option value="off">Off</option>
					<option value="low">Low</option>
					<option value="medium">Medium</option>
					<option value="high">High</option>
				</select>
			</div>
		</div>
		<label class="flex items-center gap-3">
			<input type="checkbox" bind:checked={prusaConfig.timestamp_overlay}
				class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
			<span class="text-sm text-gray-200">Timestamp overlay</span>
		</label>
		<label class="flex items-center gap-3">
			<input type="checkbox" bind:checked={prusaConfig.logo_overlay}
				class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
			<span class="text-sm text-gray-200">Logo overlay</span>
		</label>
		{#if haEntities.length}
			<div>
				<span class="mb-1 block text-sm text-gray-400">Home Assistant sensor overlay</span>
				<div class="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-gray-800 p-2">
					{#each haEntities as e}
						<label class="flex items-center gap-3">
							<input type="checkbox" checked={prusaSensorIds().includes(e.entity_id)}
								onchange={() => togglePrusaSensor(e)}
								class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
							<span class="text-sm text-gray-200">{e.label ?? e.entity_id}</span>
						</label>
					{/each}
				</div>
			</div>
		{:else}
			<p class="text-xs text-gray-500">Configure Home Assistant above to add sensor overlays.</p>
		{/if}
	</div>
</details>
```

Existing enable/generate checkboxes, deflicker option values (`off/low/medium/high` — verify against the deflicker options used by `GenerateDialog.svelte` and match them), test/save buttons stay as-is. Check the `deflicker` valid values in the backend (`_resolve`/deflicker handling in `timelapse.py` or `GenerateDialog`) and use exactly those option values.

- [ ] **Step 3b: Also verify no other frontend code references `prusaConfig.profile_id` / `.fps` / `.format`**

Run: `grep -rn "prusaProfiles\|prusaConfig.profile_id\|prusaConfig.fps\|prusaConfig.format" frontend/src`
Expected: no matches after the rework.

- [ ] **Step 4: Build check**

Run: `cd frontend && npm run check && npm run build`
Expected: no type errors, build succeeds. (If `npm run check` doesn't exist, use the script names in `frontend/package.json`.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/routes/settings/+page.svelte
git commit -m "feat(ui): camera-bound PrusaLink settings with clip + overlay config"
```

---

### Task 9: Frontend — print history on the timelapses page

**Files:**
- Modify: `frontend/src/routes/timelapses/+page.svelte`

**Interfaces:**
- Consumes: `api.getPrintJobs()`, `PrintJob` type (Task 8), existing `selectedTimelapse` player state, `formatDate`/`formatDuration` utils.

- [ ] **Step 1: Add state + loader** in the script block:

```ts
import type { PrintJob } from '$lib/types';

let printJobs = $state<PrintJob[]>([]);

async function loadPrintJobs() {
	try {
		printJobs = await api.getPrintJobs();
	} catch {
		printJobs = [];
	}
}
```

Call `loadPrintJobs()` inside the same `$effect` that calls `loadTimelapses()` (line ~60), and also re-call it wherever a `timelapse_complete` SSE event triggers `loadTimelapses()` so a freshly rendered print shows its link.

Add a play handler that reuses the modal:

```ts
function playPrintJob(pj: PrintJob) {
	const tl = timelapses.find((t) => t.id === pj.timelapse_id);
	if (tl) selectedTimelapse = tl;
}

function printDuration(pj: PrintJob): string {
	if (!pj.finished_at) return '—';
	const secs = (new Date(pj.finished_at).getTime() - new Date(pj.started_at).getTime()) / 1000;
	return formatDuration(secs);
}
```

(Verify `formatDuration`'s expected unit in `frontend/src/lib/utils.ts` — pass seconds or ms accordingly.)

- [ ] **Step 2: Add the section markup** — after the filters/header area and above the timelapse grid, gated so it only appears when there is history:

```svelte
{#if printJobs.length}
	<section class="mb-8 rounded-xl border border-gray-800 bg-gray-900 p-4">
		<h2 class="mb-3 text-lg font-semibold text-white">3D Prints</h2>
		<div class="overflow-x-auto">
			<table class="w-full text-left text-sm">
				<thead>
					<tr class="border-b border-gray-800 text-gray-400">
						<th class="py-2 pr-4 font-medium">Print</th>
						<th class="py-2 pr-4 font-medium">Status</th>
						<th class="py-2 pr-4 font-medium">Started</th>
						<th class="py-2 pr-4 font-medium">Duration</th>
						<th class="py-2 font-medium">Timelapse</th>
					</tr>
				</thead>
				<tbody>
					{#each printJobs as pj}
						<tr class="border-b border-gray-800/50 text-gray-200">
							<td class="py-2 pr-4">{pj.gcode_name || 'Untitled print'}</td>
							<td class="py-2 pr-4">
								{#if pj.status === 'printing'}
									<span class="rounded-full bg-blue-900 px-2 py-0.5 text-xs text-blue-300">Printing</span>
								{:else if pj.status === 'finished'}
									<span class="rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300">Finished</span>
								{:else}
									<span class="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300">Cancelled</span>
								{/if}
							</td>
							<td class="py-2 pr-4">{formatDate(pj.started_at)}</td>
							<td class="py-2 pr-4">{printDuration(pj)}</td>
							<td class="py-2">
								{#if pj.timelapse_id && timelapses.some((t) => t.id === pj.timelapse_id)}
									<button onclick={() => playPrintJob(pj)} class="text-blue-400 hover:text-blue-300">Play</button>
								{:else if pj.timelapse_id}
									<span class="text-gray-500">Filtered out</span>
								{:else}
									<span class="text-gray-500">—</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>
{/if}
```

Also, where the timelapse card renders its title in this page's grid, show `timelapse.name` when set (prepend/replace the period label — match the existing card markup; find it by searching this file for `period_type`).

- [ ] **Step 3: Build check** — `cd frontend && npm run check && npm run build`. Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/timelapses/+page.svelte
git commit -m "feat(ui): 3D print history with per-print timelapse playback"
```

---

### Task 10: Full-suite run, Docker verification, docs sync

**Files:**
- No new code expected; fixes only if verification finds problems.

- [ ] **Step 1: Full backend suite**

Run the full pytest command from Global Constraints (no test-file filter).
Expected: all pass except the known `test_config::test_settings_defaults` env-override failure.

- [ ] **Step 2: Docker rebuild + logs (per CLAUDE.md, with GPU override)**

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
docker compose -f docker/docker-compose.yml logs --tail=50
```

Expected: migration 029 applied cleanly, scheduler starts, no tracebacks.

- [ ] **Step 3: Chrome MCP verification** at `http://localhost:8000`:
  - Settings → 3D Printing shows Camera select (no Capture profile / FPS / Format), clip settings, both `<details>` blocks; Save round-trips.
  - Profiles page does NOT list "3D Print (auto)" after saving with a camera bound.
  - Profile templates list no longer shows the three "3D Print - *" system templates.
  - Timelapses page renders (print-history section hidden while `print_jobs` is empty).

- [ ] **Step 4: Commit any fixes, push**

```bash
git add -A && git commit -m "fix(prusalink): verification fixes" # only if changes
git push
```

- [ ] **Step 5: Trilium docs** (skip gracefully if `triliumnext-mcp` unavailable): update **Architecture** (managed profile + print_jobs flow), add dated **Changelog** entry, add **Decisions** entry: "2026-07-02 — PrusaLink binds to a camera; capture interval computed per print from PrusaLink's time estimate (managed hidden profile keeps the pipeline profile-based); seeded 3D-print templates removed."
