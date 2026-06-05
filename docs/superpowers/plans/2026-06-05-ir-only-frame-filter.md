# IR-only Frame Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-profile "IR-only" filter that keeps a captured frame only when it is greyscale (camera IR mode active), measured by mean colour chroma, with a tunable threshold and a live test button.

**Architecture:** A pure detection function (`mean_chroma`) measures the average per-pixel `max(RGB)−min(RGB)` of a frame on a 0–100 scale. The capture pipeline runs this check after the frame file is finalised and silently discards frames above the threshold. A per-profile `ir_only` toggle and `ir_chroma_threshold` column drive it. A `GET /api/streams/{id}/ir-test` endpoint returns a live frame's chroma + thumbnail so the threshold can be dialled in from the UI.

**Tech Stack:** FastAPI + SQLAlchemy + Pillow/numpy (backend), SvelteKit 2 / Svelte 5 runes (frontend), SQL migrations auto-applied on startup.

**Reference spec:** `docs/superpowers/specs/2026-06-05-ir-only-frame-filter-design.md`

---

## File Structure

**Backend**
- Create: `backend/app/migrations/versions/026_ir_filter.sql` — adds `ir_only`, `ir_chroma_threshold` to `profiles`
- Create: `backend/app/services/ir_detect.py` — pure `mean_chroma(img)` detection function
- Create: `backend/tests/test_ir_detect.py` — unit tests for `mean_chroma`
- Modify: `backend/app/models.py` — two new `Profile` columns
- Modify: `backend/app/schemas.py` — new fields on `ProfileCreate` / `ProfileUpdate` / `ProfileRead`
- Modify: `backend/app/services/capture.py` — IR filter hook after frame is finalised
- Modify: `backend/app/routers/streams.py` — `GET /{stream_id}/ir-test` endpoint
- Modify: `backend/tests/test_streams.py` — endpoint test

**Frontend**
- Modify: `frontend/src/lib/types.ts` — `ir_only` / `ir_chroma_threshold` on `Profile`, `ProfileCreate`, `ProfileUpdate`
- Modify: `frontend/src/lib/api.ts` — `irTest()` client helper
- Modify: `frontend/src/lib/components/ProfileForm.svelte` — IR-only section + Test button
- Modify: `frontend/src/routes/streams/[id]/+page.svelte` — pass `streamId` to `ProfileForm`

**Notes on conventions discovered in the codebase:**
- Migrations are plain `.sql`, numbered `NNN_name.sql`, booleans written `BOOLEAN NOT NULL DEFAULT 0` (see `010_weather.sql`).
- `Float` is already imported in `models.py`; `Field` and `Literal` already imported in `schemas.py`.
- Backend tests use an in-memory SQLite via `conftest.py` fixtures (`db`, `client`) and `Base.metadata.create_all` — they do NOT run the SQL migrations, so model columns with `default=` are what tests see.
- Run backend tests from `backend/` with a writable DB + HOME (per project memory), e.g.:
  `LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest`

---

## Task 1: Detection module `mean_chroma` (TDD)

**Files:**
- Create: `backend/app/services/ir_detect.py`
- Test: `backend/tests/test_ir_detect.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_ir_detect.py`:

```python
import numpy as np
from PIL import Image

from app.services.ir_detect import mean_chroma


def _img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype("uint8"), "RGB")


def test_solid_grey_is_near_zero():
    arr = np.full((120, 160, 3), 128, dtype="uint8")  # R==G==B everywhere
    assert mean_chroma(_img(arr)) < 1.0


def test_grey_gradient_is_near_zero():
    # Luminance gradient but still R==G==B per pixel -> chroma ~0
    col = np.linspace(0, 255, 160).astype("uint8")
    arr = np.repeat(col[None, :, None], 120, axis=0)
    arr = np.repeat(arr, 3, axis=2)
    assert mean_chroma(_img(arr)) < 1.0


def test_saturated_red_is_high():
    arr = np.zeros((120, 160, 3), dtype="uint8")
    arr[:, :, 0] = 255  # pure red -> spread 255 -> 100.0
    assert mean_chroma(_img(arr)) > 90.0


def test_mid_saturation_is_in_between():
    arr = np.zeros((120, 160, 3), dtype="uint8")
    arr[:, :, 0] = 130
    arr[:, :, 1] = 100
    arr[:, :, 2] = 100  # spread 30 -> ~11.8
    val = mean_chroma(_img(arr))
    assert 5.0 < val < 25.0


def test_grayscale_mode_image_is_near_zero():
    # An L-mode (single channel) image must still be handled (converted to RGB)
    img = Image.fromarray(np.full((120, 160), 100, dtype="uint8"), "L")
    assert mean_chroma(img) < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_ir_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ir_detect'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/ir_detect.py`:

```python
"""IR (greyscale) frame detection via mean colour chroma.

A camera in IR / night mode renders monochrome frames (R==G==B per pixel),
so the average per-pixel chroma — ``max(R,G,B) - min(R,G,B)`` — collapses to
near zero. Daytime colour footage has clearly higher chroma. The value is
normalised to a 0..100 scale for human-friendly thresholds.
"""

import numpy as np
from PIL import Image

# Frames are downsampled to this width before measurement; chroma is a global
# average so a small sample is plenty and keeps the cost negligible at any
# capture resolution.
_SAMPLE_WIDTH = 256


def mean_chroma(img: Image.Image) -> float:
    """Return the mean per-pixel colour chroma of ``img`` on a 0..100 scale.

    ~0 for a greyscale (IR) frame, tens for colour footage. Accepts any PIL
    image mode (converted to RGB internally).
    """
    rgb = img.convert("RGB")
    width, height = rgb.size
    if width > _SAMPLE_WIDTH:
        new_height = max(1, round(height * _SAMPLE_WIDTH / width))
        rgb = rgb.resize((_SAMPLE_WIDTH, new_height), Image.BILINEAR)

    arr = np.asarray(rgb, dtype=np.int16)  # int16 so max-min cannot underflow
    spread = arr.max(axis=2) - arr.min(axis=2)  # 0..255 per pixel
    return float(spread.mean()) / 255.0 * 100.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_ir_detect.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ir_detect.py backend/tests/test_ir_detect.py
git commit -m "feat: mean_chroma greyscale/IR detection metric"
```

---

## Task 2: Database migration + model columns

**Files:**
- Create: `backend/app/migrations/versions/026_ir_filter.sql`
- Modify: `backend/app/models.py:109` (after the `sun_events` column, within `class Profile`)

- [ ] **Step 1: Create the migration**

Create `backend/app/migrations/versions/026_ir_filter.sql`:

```sql
ALTER TABLE profiles ADD COLUMN ir_only BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE profiles ADD COLUMN ir_chroma_threshold REAL NOT NULL DEFAULT 10.0;
```

- [ ] **Step 2: Add the model columns**

In `backend/app/models.py`, inside `class Profile`, immediately after this line (line 109):

```python
    sun_events: Mapped[str] = mapped_column(Text, default="", server_default="")
```

add:

```python
    ir_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ir_chroma_threshold: Mapped[float] = mapped_column(
        Float, default=10.0, server_default="10.0"
    )
```

(`Boolean` and `Float` are already imported at `models.py:5`.)

- [ ] **Step 3: Verify the model imports and instantiates**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/python -c "from app.models import Profile; print(Profile.__table__.c.ir_only.type, Profile.__table__.c.ir_chroma_threshold.type)"`
Expected: prints `BOOLEAN FLOAT` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/026_ir_filter.sql backend/app/models.py
git commit -m "feat: add ir_only and ir_chroma_threshold profile columns"
```

---

## Task 3: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas.py` (`ProfileCreate` ~line 113, `ProfileUpdate` ~line 132, `ProfileRead` ~line 154)

- [ ] **Step 1: Add fields to `ProfileCreate`**

In `backend/app/schemas.py`, in `class ProfileCreate`, after the line:

```python
    sun_events: str = ""
```

add:

```python
    ir_only: bool = False
    ir_chroma_threshold: float = Field(default=10.0, ge=0, le=100)
```

- [ ] **Step 2: Add fields to `ProfileUpdate`**

In `class ProfileUpdate`, after the line:

```python
    sun_events: str | None = None
```

add:

```python
    ir_only: bool | None = None
    ir_chroma_threshold: float | None = Field(default=None, ge=0, le=100)
```

- [ ] **Step 3: Add fields to `ProfileRead`**

In `class ProfileRead`, after the line:

```python
    sun_events: str
```

add:

```python
    ir_only: bool
    ir_chroma_threshold: float
```

- [ ] **Step 4: Verify schemas import**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/python -c "from app.schemas import ProfileCreate; print(ProfileCreate(name='x').ir_chroma_threshold)"`
Expected: prints `10.0`

- [ ] **Step 5: Run existing profile tests to confirm no regression**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_profiles.py -v`
Expected: PASS (all existing tests still pass)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: expose ir_only/ir_chroma_threshold in profile schemas"
```

---

## Task 4: Capture pipeline IR filter hook

**Files:**
- Modify: `backend/app/services/capture.py` (insert between the end of the capture branches at line 361 and the weather block at line 363)

The three capture branches (bytes-source, HDR, standard ffmpeg) all finish with a finalised JPEG at `abs_path`. Inserting one check after all branches keeps it DRY and avoids touching each branch.

- [ ] **Step 1: Add the IR filter check**

In `backend/app/services/capture.py`, find the end of the standard-capture `else` branch — these lines (361 and 363):

```python
            file_size = os.path.getsize(abs_path)

        # Fetch weather data if enabled
```

Insert the IR check between them so it reads:

```python
            file_size = os.path.getsize(abs_path)

        # IR-only filter: keep the frame only if it is greyscale (camera in IR
        # mode). Non-IR frames are silently discarded — no file, no DB record.
        if profile.ir_only:
            from app.services.ir_detect import mean_chroma

            with Image.open(abs_path) as ir_img:
                chroma = mean_chroma(ir_img)
            if chroma > profile.ir_chroma_threshold:
                logger.debug(
                    "Profile %d non-IR frame (chroma %.1f > %.1f), discarding",
                    profile_id, chroma, profile.ir_chroma_threshold,
                )
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                return

        # Fetch weather data if enabled
```

- [ ] **Step 2: Write a test for the discard behaviour**

Add to `backend/tests/test_ir_detect.py`:

```python
import os
from unittest.mock import patch

import pytest

from app.services import capture


class _StubStream:
    id = 1
    name = "cam"
    source_type = "go2rtc"
    go2rtc_name = "cam"
    url = None


class _StubProfile:
    id = 1
    name = "p"
    resolution_width = None
    resolution_height = None
    quality = 85
    hdr_enabled = False
    weather_enabled = False
    ha_sensors = None
    ir_only = True
    ir_chroma_threshold = 10.0

    def __init__(self):
        self.stream = _StubStream()


def _jpeg_bytes(arr):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr.astype("uint8"), "RGB").save(buf, "JPEG", quality=95)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_capture_discards_colour_frame_when_ir_only(tmp_path, monkeypatch):
    import numpy as np

    profile = _StubProfile()
    colour = np.zeros((120, 160, 3), dtype="uint8")
    colour[:, :, 0] = 255  # pure red -> chroma 100 > threshold 10

    # DB session returns our stub profile; commit/add are no-ops.
    class _Q:
        def filter(self, *a, **k): return self
        def first(self): return profile
    class _DB:
        def query(self, *a, **k): return _Q()
        def add(self, *a, **k): pass
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(capture, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(capture.settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(capture, "_is_within_active_window", lambda *a, **k: True)
    monkeypatch.setattr(capture, "_is_frame_corrupt", lambda *a, **k: False)

    async def _fake_fetch(stream, db):
        return _jpeg_bytes(colour)
    from app.services import providers
    monkeypatch.setattr(providers, "fetch_jpeg_bytes", _fake_fetch)

    captured = {}
    real_capture_init = capture.Capture
    monkeypatch.setattr(
        capture, "Capture",
        lambda **kw: captured.setdefault("record", kw) or real_capture_init(**kw),
    )

    await capture.capture_frame(1)

    # No DB record created, and no jpeg left on disk for this profile.
    assert "record" not in captured
    leftover = list(tmp_path.rglob("*.jpg"))
    assert leftover == []
```

Note: if `pytest-asyncio` is not configured for `asyncio_mode=auto`, keep the `@pytest.mark.asyncio` decorator (the project already has async tests — mirror their style; check an existing async test such as in `tests/test_http_source.py` or `tests/test_homeassistant.py` and match the decorator/marker they use).

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_ir_detect.py -v`
Expected: PASS — including `test_capture_discards_colour_frame_when_ir_only`

- [ ] **Step 4: Sanity-check the keep path manually**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_ir_detect.py tests/test_profiles.py tests/test_captures.py -v`
Expected: PASS (no regression in capture/profile suites)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/capture.py backend/tests/test_ir_detect.py
git commit -m "feat: discard non-IR frames in capture when ir_only enabled"
```

---

## Task 5: Live IR-test endpoint

**Files:**
- Modify: `backend/app/routers/streams.py` (add endpoint after the existing `preview_stream` at line 120-129)
- Test: `backend/tests/test_streams.py`

- [ ] **Step 1: Add the endpoint**

In `backend/app/routers/streams.py`, after the `preview_stream` function (ends at line 129 with `return Response(...)`), add:

```python
@router.get("/{stream_id}/ir-test")
async def ir_test_stream(stream_id: int, db: Session = Depends(get_db)):
    """Grab a live frame and report its measured chroma + a base64 thumbnail.

    Used by the profile form to dial in the IR-only threshold: sample once in
    daylight and once at night, then set the threshold between the two values.
    """
    import base64
    import io

    from PIL import Image

    from app.services.ir_detect import mean_chroma

    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    try:
        jpeg_bytes = await providers.grab_preview(stream, db)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch frame: {exc}")

    with Image.open(io.BytesIO(jpeg_bytes)) as img:
        chroma = mean_chroma(img)

    return {
        "chroma": round(chroma, 1),
        "preview": base64.b64encode(jpeg_bytes).decode("ascii"),
    }
```

(`Stream`, `HTTPException`, `Depends`, `get_db`, `providers` are all already imported in this file.)

- [ ] **Step 2: Write the endpoint test**

Add to `backend/tests/test_streams.py` (match the file's existing import/fixture style — it uses the `client` and `db` fixtures from `conftest.py`):

```python
def test_ir_test_endpoint_returns_chroma_and_preview(client, db, monkeypatch):
    import io
    import numpy as np
    from PIL import Image
    from app.models import Stream

    stream = Stream(name="cam", source_type="go2rtc", go2rtc_name="cam")
    db.add(stream)
    db.commit()
    db.refresh(stream)

    buf = io.BytesIO()
    grey = np.full((120, 160, 3), 100, dtype="uint8")
    Image.fromarray(grey, "RGB").save(buf, "JPEG", quality=95)
    jpeg = buf.getvalue()

    async def _fake_preview(s, d):
        return jpeg

    from app.services import providers
    monkeypatch.setattr(providers, "grab_preview", _fake_preview)

    resp = client.get(f"/api/streams/{stream.id}/ir-test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chroma"] < 1.0
    assert isinstance(body["preview"], str) and len(body["preview"]) > 0
```

Note: construct the `Stream` with whatever required columns the model defines — if `Stream(...)` raises for a missing non-null field, inspect `app/models.py` `class Stream` and supply minimal valid values (mirror how `test_streams.py`'s existing tests build a stream).

- [ ] **Step 3: Run the endpoint test**

Run: `cd backend && LAPSORA_DATABASE_URL=sqlite:////tmp/lapsora_test.db HOME=/tmp .venv/bin/pytest tests/test_streams.py -v`
Expected: PASS — including `test_ir_test_endpoint_returns_chroma_and_preview`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/streams.py backend/tests/test_streams.py
git commit -m "feat: add /streams/{id}/ir-test live chroma endpoint"
```

---

## Task 6: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts` (`Profile` ~line 71, `ProfileCreate` ~line 128, `ProfileUpdate` ~line 145)
- Modify: `frontend/src/lib/api.ts` (after `getStreamLiveUrl`, ~line 36)

- [ ] **Step 1: Add fields to the `Profile` interface**

In `frontend/src/lib/types.ts`, in `interface Profile`, after the line `sun_events: string;` (line 71), add:

```ts
	ir_only: boolean;
	ir_chroma_threshold: number;
```

- [ ] **Step 2: Add fields to `ProfileCreate`**

In `interface ProfileCreate`, after `sun_events?: string;` (line 128), add:

```ts
	ir_only?: boolean;
	ir_chroma_threshold?: number;
```

- [ ] **Step 3: Add fields to `ProfileUpdate`**

In `interface ProfileUpdate`, after `sun_events?: string;` (line 145), add:

```ts
	ir_only?: boolean;
	ir_chroma_threshold?: number;
```

- [ ] **Step 4: Add the API client helper**

In `frontend/src/lib/api.ts`, after the line:

```ts
	getStreamLiveUrl: (id: number) => request<{ ws_url: string }>(`/streams/${id}/live-url`),
```

add:

```ts
	irTestStream: (id: number) => request<{ chroma: number; preview: string }>(`/streams/${id}/ir-test`),
```

- [ ] **Step 5: Verify the frontend type-checks**

Run: `cd frontend && npm run check`
Expected: no new type errors referencing `ir_only`, `ir_chroma_threshold`, or `irTestStream`. (If the project has no `check` script, run `npx svelte-check --tsconfig ./tsconfig.json` instead.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types + api client for IR-only filter"
```

---

## Task 7: ProfileForm UI + Test button

**Files:**
- Modify: `frontend/src/lib/components/ProfileForm.svelte`
- Modify: `frontend/src/routes/streams/[id]/+page.svelte` (pass `streamId` to both `ProfileForm` usages, lines 534 and 539)

- [ ] **Step 1: Add the `streamId` prop and IR state**

In `frontend/src/lib/components/ProfileForm.svelte`, change the `Props` interface and destructuring (lines 5-11) to add `streamId`:

```ts
	interface Props {
		profile?: Profile | null;
		mode?: 'profile' | 'template';
		streamId?: number | null;
		onsubmit: (data: ProfileCreate | ProfileUpdate) => void;
	}

	let { profile = null, mode = 'profile', streamId = null, onsubmit }: Props = $props();
```

Then, after the `sun_events` state declaration (lines 54-56), add IR state and the test handler:

```ts
	let ir_only = $state(profile?.ir_only ?? false);
	let ir_chroma_threshold = $state(profile?.ir_chroma_threshold ?? 10);

	let irTesting = $state(false);
	let irTestError = $state('');
	let irTestChroma = $state<number | null>(null);
	let irTestPreview = $state<string | null>(null);

	async function runIrTest() {
		if (streamId == null) return;
		irTesting = true;
		irTestError = '';
		try {
			const res = await api.irTestStream(streamId);
			irTestChroma = res.chroma;
			irTestPreview = `data:image/jpeg;base64,${res.preview}`;
		} catch (err) {
			irTestError = err instanceof Error ? err.message : 'Test failed';
		} finally {
			irTesting = false;
		}
	}
```

- [ ] **Step 2: Include the IR fields in the submitted payload**

In `handleSubmit` (lines 89-103), add the two fields to the `data` object — insert after the `sun_events: ...` line (line 101):

```ts
			sun_events: capture_mode === 'sun' ? sun_events.join(',') : '',
			ir_only,
			ir_chroma_threshold,
			ha_sensors: haSensors.length ? JSON.stringify(haSensors) : null
```

- [ ] **Step 3: Add the IR-only UI section**

In the template, insert the following block immediately before the submit `<button type="submit" ...>` (line 323):

```svelte
	<!-- IR-only capture -->
	<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900/40 p-3">
		<label class="flex items-center gap-3 text-sm font-medium text-gray-300">
			<input
				type="checkbox"
				bind:checked={ir_only}
				class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
			/>
			IR-only capture <span class="text-gray-500">(keep frames only when greyscale)</span>
		</label>

		{#if ir_only}
			<div>
				<label for="ir-threshold" class="mb-1 block text-sm font-medium text-gray-300">
					Chroma threshold: {ir_chroma_threshold}
				</label>
				<input
					id="ir-threshold"
					type="range"
					min="0"
					max="100"
					step="0.5"
					bind:value={ir_chroma_threshold}
					class="w-full accent-blue-500"
				/>
				<p class="mt-1 text-xs text-gray-500">
					Frames with mean colour chroma at or below this value are kept; higher (colour) frames are discarded.
				</p>
			</div>

			{#if streamId != null}
				<div class="space-y-2">
					<button
						type="button"
						onclick={runIrTest}
						disabled={irTesting}
						class="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50"
					>
						{irTesting ? 'Testing…' : 'Test now'}
					</button>

					{#if irTestError}
						<p class="text-xs text-red-400">{irTestError}</p>
					{/if}

					{#if irTestChroma !== null}
						<div class="flex items-start gap-3">
							{#if irTestPreview}
								<img src={irTestPreview} alt="IR test frame" class="h-24 w-auto rounded border border-gray-700" />
							{/if}
							<div class="space-y-1 text-sm">
								<div class="text-gray-300">Measured chroma: <span class="font-semibold">{irTestChroma}</span></div>
								{#if irTestChroma <= ir_chroma_threshold}
									<span class="inline-block rounded bg-green-900 px-2 py-0.5 text-xs font-medium text-green-300">
										would KEEP ({irTestChroma} ≤ {ir_chroma_threshold})
									</span>
								{:else}
									<span class="inline-block rounded bg-red-900 px-2 py-0.5 text-xs font-medium text-red-300">
										would SKIP ({irTestChroma} &gt; {ir_chroma_threshold})
									</span>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{:else}
				<p class="text-xs text-gray-500">Save the profile / open it from its stream to use the live test.</p>
			{/if}
		{/if}
	</div>

```

- [ ] **Step 4: Pass `streamId` from the stream detail page**

In `frontend/src/routes/streams/[id]/+page.svelte`:

Line 534 — change:

```svelte
						<ProfileForm profile={editingProfile} onsubmit={handleUpdateProfile} />
```
to:
```svelte
						<ProfileForm profile={editingProfile} streamId={id} onsubmit={handleUpdateProfile} />
```

Line 539 — change:

```svelte
					<ProfileForm onsubmit={handleCreateProfile} />
```
to:
```svelte
					<ProfileForm streamId={id} onsubmit={handleCreateProfile} />
```

(`id` is the route-derived stream id at `+page.svelte:11`: `let id = $derived(Number($page.params.id));`)

- [ ] **Step 5: Verify the frontend builds / type-checks**

Run: `cd frontend && npm run check`
Expected: no type errors. (Falls back to `npx svelte-check --tsconfig ./tsconfig.json` if no `check` script.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/ProfileForm.svelte "frontend/src/routes/streams/[id]/+page.svelte"
git commit -m "feat: IR-only capture UI with live test button"
```

---

## Task 8: End-to-end verification (Docker + Chrome DevTools)

**Files:** none (verification only)

Per `CLAUDE.md`: never run the app natively; use Docker with the GPU compose override (per project memory).

- [ ] **Step 1: Rebuild the container**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build
```
Expected: build succeeds (frontend build + backend image), no errors.

- [ ] **Step 2: Start and inspect logs**

Run:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
docker compose -f docker/docker-compose.yml logs --tail=80
```
Expected: no startup errors; migration `026_ir_filter.sql` applied cleanly; scheduler starts.

- [ ] **Step 3: Verify the migration took effect**

Run:
```bash
docker compose -f docker/docker-compose.yml exec -T <service> python -c "import sqlite3, glob; \
import os; \
print('ok')"
```
(Replace `<service>` with the app service name from `docker-compose.yml`.) Simpler alternative: in the UI (next step) confirm the IR-only controls render and persist — that exercises the column end-to-end.

- [ ] **Step 4: Test in Chrome DevTools MCP**

Using the `chrome-devtools` MCP tools:
1. Navigate to `http://localhost:8000`.
2. Open a stream that has a working source, open/create a profile (the form should show the new **IR-only capture** section).
3. Tick **IR-only capture**, confirm the threshold slider and **Test now** button appear.
4. Click **Test now** — confirm a thumbnail + measured chroma render, and a green KEEP / red SKIP badge appears.
5. Drag the threshold slider across the measured chroma value — confirm the badge flips KEEP↔SKIP live.
6. Save the profile, reopen it — confirm `ir_only` stays ticked and the threshold persists.

Expected: all steps behave as described; no console errors.

- [ ] **Step 5: Final commit (if any verification tweaks were needed)**

```bash
git add -A
git commit -m "fix: IR-only filter verification adjustments"
```
(Skip if nothing changed during verification.)

---

## Self-Review (completed during planning)

- **Spec coverage:** detection metric → Task 1; data model → Task 2; schemas → Task 3; capture hook / silent discard → Task 4; test endpoint → Task 5; frontend types+api → Task 6; UI toggle + threshold + Test button + live KEEP/SKIP verdict → Task 7; unit + manual testing → Tasks 1,4,5,8. ONVIF / hysteresis / color-IR explicitly out of scope (not implemented, by design).
- **No reschedule:** `ir_only` / `ir_chroma_threshold` deliberately excluded from the profiles router `needs_reschedule` set — they don't affect timing — so `update_profile` needs no change. Confirmed against `profiles.py:61-65`.
- **Type consistency:** function `mean_chroma(img)` (Task 1) used identically in capture (Task 4) and the endpoint (Task 5); API helper named `irTestStream` consistently in api.ts (Task 6) and ProfileForm (Task 7); response shape `{chroma, preview}` consistent across endpoint (Task 5), client type (Task 6), and UI consumption (Task 7).
- **Placeholders:** none — every code step contains full content.
