# Time Range Picker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the broken `datetime-local` inputs in GenerateDialog with preset chips + cross-browser date/time inputs.

**Architecture:** Single-component change. Add preset chip row that computes date ranges client-side. Replace `datetime-local` with split `date` + `time` inputs for custom mode. No backend changes.

**Tech Stack:** Svelte 5 (runes), Tailwind CSS, native HTML date/time inputs.

---

### Task 1: Add preset state and computation logic

**Files:**
- Modify: `frontend/src/lib/components/GenerateDialog.svelte:12-14`

**Step 1: Replace period_start/period_end state with preset-driven state**

Replace lines 12-14:
```typescript
let period_start = $state('');
let period_end = $state('');
```

With:
```typescript
type Preset = 'last24h' | 'today' | 'yesterday' | 'last7d' | 'last30d' | 'thisWeek' | 'lastWeek' | 'custom';

const PRESETS: { key: Preset; label: string }[] = [
	{ key: 'last24h', label: 'Last 24h' },
	{ key: 'today', label: 'Today' },
	{ key: 'yesterday', label: 'Yesterday' },
	{ key: 'last7d', label: 'Last 7d' },
	{ key: 'last30d', label: 'Last 30d' },
	{ key: 'thisWeek', label: 'This week' },
	{ key: 'lastWeek', label: 'Last week' },
	{ key: 'custom', label: 'Custom' },
];

let selectedPreset = $state<Preset>('last24h');
let customStartDate = $state('');
let customStartTime = $state('00:00');
let customEndDate = $state('');
let customEndTime = $state('23:59');

function computePresetRange(preset: Preset): { start: string; end: string } | null {
	const now = new Date();
	let start: Date;
	let end: Date = now;

	switch (preset) {
		case 'last24h':
			start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			break;
		case 'today':
			start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			break;
		case 'yesterday': {
			const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
			start = y;
			end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			break;
		}
		case 'last7d':
			start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
			break;
		case 'last30d':
			start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
			break;
		case 'thisWeek': {
			const day = now.getDay();
			const diff = day === 0 ? 6 : day - 1; // Monday = 0
			start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
			break;
		}
		case 'lastWeek': {
			const day = now.getDay();
			const diff = day === 0 ? 6 : day - 1;
			const thisMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
			start = new Date(thisMonday.getTime() - 7 * 24 * 60 * 60 * 1000);
			end = new Date(thisMonday.getTime() - 1000); // Sunday 23:59:59
			break;
		}
		case 'custom':
			return null;
	}

	return {
		start: start.toISOString().slice(0, 19),
		end: end.toISOString().slice(0, 19),
	};
}

let period_start = $derived.by(() => {
	if (selectedPreset === 'custom') {
		if (!customStartDate) return '';
		return `${customStartDate}T${customStartTime || '00:00'}:00`;
	}
	return computePresetRange(selectedPreset)?.start ?? '';
});

let period_end = $derived.by(() => {
	if (selectedPreset === 'custom') {
		if (!customEndDate) return '';
		return `${customEndDate}T${customEndTime || '23:59'}:00`;
	}
	return computePresetRange(selectedPreset)?.end ?? '';
});
```

**Step 2: Verify no TypeScript errors**

Run: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build 2>&1 | tail -5`
Expected: Build succeeds (the `period_start`/`period_end` derived values feed into `handleSubmit` the same way as before).

**Step 3: Commit**

```bash
git add frontend/src/lib/components/GenerateDialog.svelte
git commit -m "feat(generate): add preset computation logic for time range picker"
```

---

### Task 2: Replace datetime-local inputs with preset chips + split inputs

**Files:**
- Modify: `frontend/src/lib/components/GenerateDialog.svelte:151-169` (the Start/End input section)

**Step 1: Replace the Start/End datetime-local inputs**

Replace lines 151-169 (the two `<div>` blocks containing `datetime-local` inputs) with:

```svelte
<div>
	<label class="mb-1.5 block text-sm font-medium text-gray-300">Time Range</label>
	<div class="flex flex-wrap gap-1.5">
		{#each PRESETS as preset}
			<button
				type="button"
				onclick={() => { selectedPreset = preset.key; }}
				class="rounded-full px-3 py-1 text-xs font-medium transition-colors {
					selectedPreset === preset.key
						? 'bg-blue-600 text-white'
						: 'bg-gray-700 text-gray-300 hover:bg-gray-600'
				}"
			>
				{preset.label}
			</button>
		{/each}
	</div>
</div>

{#if selectedPreset === 'custom'}
	<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
		<div>
			<label for="gen-start-date" class="mb-1 block text-sm font-medium text-gray-300">Start</label>
			<div class="flex gap-2">
				<input
					id="gen-start-date"
					type="date"
					bind:value={customStartDate}
					class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
				<input
					id="gen-start-time"
					type="time"
					bind:value={customStartTime}
					class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
			</div>
		</div>
		<div>
			<label for="gen-end-date" class="mb-1 block text-sm font-medium text-gray-300">End</label>
			<div class="flex gap-2">
				<input
					id="gen-end-date"
					type="date"
					bind:value={customEndDate}
					class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
				<input
					id="gen-end-time"
					type="time"
					bind:value={customEndTime}
					class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
			</div>
		</div>
	</div>
{/if}
```

**Step 2: Build and verify**

Run: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml build 2>&1 | tail -5`
Expected: Build succeeds.

**Step 3: Start container and visually verify**

Run: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d`

Verify in browser:
1. Open Generate dialog — preset chips appear, "Last 24h" highlighted blue
2. Click different presets — highlight moves
3. Click "Custom" — date/time inputs appear
4. All inputs render correctly (no Firefox `datetime-local` issue)

**Step 4: Commit**

```bash
git add frontend/src/lib/components/GenerateDialog.svelte
git commit -m "feat(generate): replace datetime-local with preset chips and split date/time inputs"
```

---

### Task 3: End-to-end verification and push

**Step 1: Test preset generation**

1. Open Generate dialog, leave "Last 24h" selected
2. Click Generate — should succeed (or fail with "no captures" if none in last 24h, which is expected)
3. Try "Last 7d" — trigger generation, verify it uses the correct date range

**Step 2: Test custom range generation**

1. Select "Custom" chip
2. Enter a date range known to have captures
3. Click Generate — verify it works

**Step 3: Test in Firefox (if available) or verify date/time inputs render correctly**

The key fix: `<input type="date">` and `<input type="time">` both work in Firefox, unlike `<input type="datetime-local">`.

**Step 4: Push**

```bash
git push
```
