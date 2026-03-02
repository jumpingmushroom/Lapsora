# Sun Events Capture Mode — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the "sun" capture mode with selectable sun events (daylight, golden hour, blue hour, night) so users can capture only during specific astronomical windows.

**Architecture:** Add a `sun_events` comma-separated text column to profiles. Refactor the sun branch in `_is_within_active_window()` to compute time windows using `astral` and check if now falls within any selected event. Add checkbox UI in ProfileForm.

**Tech Stack:** Python/FastAPI, astral library (already installed), Svelte 5 runes, SQLite

---

### Task 1: Database Migration

**Files:**
- Create: `backend/app/migrations/versions/014_sun_events.sql`

**Step 1: Create migration file**

```sql
ALTER TABLE profiles ADD COLUMN sun_events TEXT NOT NULL DEFAULT '';
```

**Step 2: Commit**

```bash
git add backend/app/migrations/versions/014_sun_events.sql
git commit -m "feat: add sun_events column to profiles"
```

---

### Task 2: Backend Model & Schemas

**Files:**
- Modify: `backend/app/models.py:67` (Profile class, after `sun_offset_minutes`)
- Modify: `backend/app/schemas.py:60-64` (ProfileCreate), `backend/app/schemas.py:78` (ProfileUpdate), `backend/app/schemas.py:98` (ProfileRead)

**Step 1: Add column to Profile model**

In `backend/app/models.py`, after `sun_offset_minutes` line in the `Profile` class, add:

```python
sun_events: Mapped[str] = mapped_column(Text, default="", server_default="")
```

**Step 2: Add to schemas**

In `backend/app/schemas.py`:

- `ProfileCreate` — add after `sun_offset_minutes`:
  ```python
  sun_events: str = ""
  ```

- `ProfileUpdate` — add after `sun_offset_minutes`:
  ```python
  sun_events: str | None = None
  ```

- `ProfileRead` — add after `sun_offset_minutes`:
  ```python
  sun_events: str
  ```

**Step 3: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py
git commit -m "feat: add sun_events to Profile model and schemas"
```

---

### Task 3: Refactor Capture Service Sun Logic

**Files:**
- Modify: `backend/app/services/capture.py:89-122` (`_is_within_active_window` function)

**Step 1: Replace the sun branch in `_is_within_active_window()`**

Replace lines 94-108 (the `if profile.capture_mode == "sun":` block) with:

```python
if profile.capture_mode == "sun":
    try:
        from astral import LocationInfo
        from astral.sun import sun

        lat_row = db.query(Setting).filter(Setting.key == "location_latitude").first()
        lon_row = db.query(Setting).filter(Setting.key == "location_longitude").first()
        if not lat_row or not lon_row:
            return True  # No location configured, allow capture
        lat, lon = float(lat_row.value), float(lon_row.value)
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=now.date())
        offset = timedelta(minutes=profile.sun_offset_minutes)

        # Parse selected sun events, default to daylight
        events = set(e.strip() for e in profile.sun_events.split(",") if e.strip()) if profile.sun_events else set()
        if not events:
            events = {"daylight"}

        # Build list of (start, end) time windows
        windows: list[tuple] = []

        sunrise = s["sunrise"]
        sunset = s["sunset"]

        # Get civil twilight times for blue hour / night
        from astral.sun import dawn, dusk
        try:
            civil_dawn = dawn(loc.observer, date=now.date(), depression=6)
            civil_dusk = dusk(loc.observer, date=now.date(), depression=6)
        except ValueError:
            # Polar regions — sun never sets or never rises
            civil_dawn = sunrise
            civil_dusk = sunset

        if "daylight" in events:
            windows.append(((sunrise - offset).time(), (sunset + offset).time()))

        if "golden_hour" in events:
            windows.append(((sunrise - offset).time(), (sunrise + timedelta(hours=1) + offset).time()))
            windows.append(((sunset - timedelta(hours=1) - offset).time(), (sunset + offset).time()))

        if "blue_hour" in events:
            windows.append(((civil_dawn - offset).time(), (sunrise + offset).time()))
            windows.append(((sunset - offset).time(), (civil_dusk + offset).time()))

        if "night" in events:
            windows.append(((civil_dusk - offset).time(), (civil_dawn + offset).time()))

        if not windows:
            return True  # No windows computed, allow capture

        # Check if current time falls within any window
        current = now.time()
        for win_start, win_end in windows:
            if win_start <= win_end:
                if win_start <= current <= win_end:
                    return True
            else:  # overnight span
                if current >= win_start or current <= win_end:
                    return True
        return False

    except Exception:
        logger.warning("Failed to compute sun times for profile %d, allowing capture", profile.id)
        return True
```

Note: The `current = now.time()` line and the start/end comparison at lines 118-122 are now handled inside the sun block, so the shared comparison code after the if/elif/else needs to remain only for the `manual` branch. Restructure accordingly — the manual branch should keep its own comparison:

```python
else:  # manual
    if not profile.active_start_time or not profile.active_end_time:
        return True
    start = datetime.strptime(profile.active_start_time, "%H:%M").time()
    end = datetime.strptime(profile.active_end_time, "%H:%M").time()
    current = now.time()
    if start <= end:
        return start <= current <= end
    else:
        return current >= start or current <= end
```

**Step 2: Commit**

```bash
git add backend/app/services/capture.py
git commit -m "feat: support sun events (golden hour, blue hour, night) in capture window"
```

---

### Task 4: Frontend Types

**Files:**
- Modify: `frontend/src/lib/types.ts`

**Step 1: Add sun_events to TypeScript interfaces**

- `Profile` interface — add after `sun_offset_minutes`:
  ```typescript
  sun_events: string;
  ```

- `ProfileCreate` interface — add after `sun_offset_minutes`:
  ```typescript
  sun_events?: string;
  ```

- `ProfileUpdate` interface — add after `sun_offset_minutes`:
  ```typescript
  sun_events?: string;
  ```

**Step 2: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat: add sun_events to frontend type definitions"
```

---

### Task 5: Frontend ProfileForm UI

**Files:**
- Modify: `frontend/src/lib/components/ProfileForm.svelte`

**Step 1: Add sun_events state variable**

After the `sun_offset_minutes` state declaration (line 22), add:

```typescript
let sun_events = $state<string[]>(
    profile?.sun_events ? profile.sun_events.split(',').filter(Boolean) : ['daylight']
);
```

**Step 2: Include sun_events in form submission**

In the `handleSubmit` function, add to the data object after `sun_offset_minutes`:

```typescript
sun_events: capture_mode === 'sun' ? sun_events.join(',') : ''
```

**Step 3: Add checkbox group UI**

Inside the `{#if capture_mode === 'sun'}` block (after the offset input div, before `{/if}`), add:

```svelte
<div class="mt-3">
    <label class="mb-2 block text-sm font-medium text-gray-300">Sun events</label>
    <div class="space-y-2 rounded-md border border-gray-700 bg-gray-900 p-3">
        <label class="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" value="daylight" bind:group={sun_events} class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500" />
            Daylight <span class="text-gray-500">(sunrise to sunset)</span>
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" value="golden_hour" bind:group={sun_events} class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500" />
            Golden hour <span class="text-gray-500">(warm light after sunrise / before sunset)</span>
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" value="blue_hour" bind:group={sun_events} class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500" />
            Blue hour <span class="text-gray-500">(twilight before sunrise / after sunset)</span>
        </label>
        <label class="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" value="night" bind:group={sun_events} class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500" />
            Night <span class="text-gray-500">(dusk to dawn)</span>
        </label>
    </div>
    <p class="mt-1 text-xs text-gray-500">Select which parts of the day to capture. Multiple selections are combined.</p>
</div>
```

**Step 4: Commit**

```bash
git add frontend/src/lib/components/ProfileForm.svelte
git commit -m "feat: add sun events checkbox group to profile form"
```

---

### Task 6: Build, Verify & Push

**Step 1: Build Docker container**

```bash
docker compose -f docker/docker-compose.yml build
```

**Step 2: Start and check logs**

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml logs -f --tail=50
```

Verify: no startup errors, migration 014 applied, scheduler starts.

**Step 3: Verify in browser**

- Navigate to a stream's profile edit form
- Set capture mode to "Sunrise/Sunset"
- Confirm the sun events checkbox group appears below the offset input
- Check "Golden hour" and "Blue hour", uncheck "Daylight"
- Save the profile
- Re-open the profile — confirm selections persist

**Step 4: Verify an existing sun-mode profile still works**

- Open an existing profile that uses sun mode
- Confirm sun_events shows "Daylight" checked (backward compat default)
- Save without changes — confirm no errors

**Step 5: Final commit and push**

```bash
git push
```
