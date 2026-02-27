<script lang="ts">
	import { api } from '$lib/api';
	import type { CleanupSchedule, Profile } from '$lib/types';

	let schedules = $state<CleanupSchedule[]>([]);
	let profiles = $state<Profile[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Add form state
	let showForm = $state(false);
	let formProfileId = $state<number | null>(null);
	let formName = $state('');
	let formCaptureDays = $state(32);
	let formTimelapseDays = $state(90);
	let formCron = $state('0 3 * * *');
	let formPreset = $state<string | null>('daily');
	let formCustom = $state(false);
	let saving = $state(false);
	let editingId = $state<number | null>(null);

	const PRESETS: Record<string, { label: string; cron: string; description: string }> = {
		daily: { label: 'Daily 03:00', cron: '0 3 * * *', description: 'Every day at 03:00' },
		weekly: { label: 'Weekly Sun 03:00', cron: '0 3 * * 0', description: 'Sunday at 03:00' }
	};

	async function load() {
		loading = true;
		error = null;
		try {
			const [s, streams] = await Promise.all([
				api.getCleanupSchedules(),
				api.getStreams()
			]);
			schedules = s;
			const allProfiles: Profile[] = [];
			await Promise.all(
				streams.map(async (st) => {
					const p = await api.getStreamProfiles(st.id);
					allProfiles.push(...p);
				})
			);
			profiles = allProfiles;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		load();
	});

	function openForm() {
		editingId = null;
		formProfileId = profiles.length > 0 ? profiles[0].id : null;
		formName = '';
		formCaptureDays = 32;
		formTimelapseDays = 90;
		formPreset = 'daily';
		formCron = '0 3 * * *';
		formCustom = false;
		showForm = true;
	}

	function openEdit(schedule: CleanupSchedule) {
		editingId = schedule.id;
		formProfileId = schedule.profile_id;
		formName = schedule.name || '';
		formCaptureDays = schedule.capture_retention_days;
		formTimelapseDays = schedule.timelapse_retention_days;
		formCron = schedule.cron_expression;
		// Detect if cron matches a preset
		const matchedPreset = Object.entries(PRESETS).find(([, info]) => info.cron === schedule.cron_expression);
		if (matchedPreset) {
			formPreset = matchedPreset[0];
			formCustom = false;
		} else {
			formPreset = null;
			formCustom = true;
		}
		showForm = true;
	}

	function selectPreset(key: string) {
		formPreset = key;
		formCron = PRESETS[key].cron;
		formCustom = false;
	}

	function selectCustom() {
		formPreset = null;
		formCron = '';
		formCustom = true;
	}

	async function saveSchedule() {
		if (!formProfileId) return;
		if (!formCron) {
			alert('Please enter a cron expression');
			return;
		}
		saving = true;
		try {
			if (editingId) {
				await api.updateCleanupSchedule(editingId, {
					name: formName,
					capture_retention_days: formCaptureDays,
					timelapse_retention_days: formTimelapseDays,
					cron_expression: formCron
				});
			} else {
				await api.createCleanupSchedule({
					profile_id: formProfileId,
					name: formName,
					capture_retention_days: formCaptureDays,
					timelapse_retention_days: formTimelapseDays,
					cron_expression: formCron
				});
			}
			showForm = false;
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save');
		} finally {
			saving = false;
		}
	}

	async function toggleEnabled(schedule: CleanupSchedule) {
		try {
			await api.updateCleanupSchedule(schedule.id, { enabled: !schedule.enabled });
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update');
		}
	}

	async function deleteSchedule(id: number) {
		if (!confirm('Delete this cleanup schedule?')) return;
		try {
			await api.deleteCleanupSchedule(id);
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete');
		}
	}

	async function triggerNow(id: number) {
		try {
			const result = await api.triggerCleanupSchedule(id);
			alert(result.message || 'Cleanup triggered');
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to trigger');
		}
	}

	function describeCron(schedule: CleanupSchedule): string {
		for (const [, info] of Object.entries(PRESETS)) {
			if (schedule.cron_expression === info.cron) return info.description;
		}
		return schedule.cron_expression;
	}

	function formatNextRun(iso: string | null): string {
		if (!iso) return 'N/A';
		return new Date(iso).toLocaleString();
	}

	function profileName(id: number): string {
		const p = profiles.find((p) => p.id === id);
		return p ? p.name : `Profile #${id}`;
	}
</script>

<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
	<div class="mb-4 flex items-center justify-between">
		<h2 class="text-lg font-semibold text-white">Cleanup Schedules</h2>
		<button
			onclick={openForm}
			class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			Add Schedule
		</button>
	</div>

	{#if loading}
		<p class="text-sm text-gray-400">Loading cleanup schedules...</p>
	{:else if error}
		<p class="text-sm text-red-400">{error}</p>
	{:else if schedules.length === 0}
		<p class="text-sm text-gray-500">No cleanup schedules configured. Captures and timelapses will be kept indefinitely.</p>
	{:else}
		<div class="space-y-3">
			{#each schedules as schedule}
				<div class="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 p-3">
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span class="font-medium text-gray-100">{schedule.name || 'Cleanup'}</span>
							<span class="text-xs text-gray-500">{profileName(schedule.profile_id)}</span>
						</div>
						<div class="mt-1 flex items-center gap-3 text-xs text-gray-400">
							<span>{describeCron(schedule)}</span>
							<span>Captures: {schedule.capture_retention_days}d</span>
							<span>Timelapses: {schedule.timelapse_retention_days}d</span>
							{#if schedule.next_run}
								<span>Next: {formatNextRun(schedule.next_run)}</span>
							{/if}
						</div>
					</div>
					<div class="ml-3 flex items-center gap-2">
						<button
							onclick={() => openEdit(schedule)}
							title="Edit"
							class="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-700 hover:text-gray-200"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
							</svg>
						</button>
						<button
							onclick={() => triggerNow(schedule.id)}
							title="Run now"
							class="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-700 hover:text-gray-200"
						>
							<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
						</button>
						<button
							onclick={() => toggleEnabled(schedule)}
							title={schedule.enabled ? 'Disable' : 'Enable'}
							class="rounded p-1.5 transition-colors {schedule.enabled ? 'text-green-400 hover:text-green-300' : 'text-gray-600 hover:text-gray-400'} hover:bg-gray-700"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								{#if schedule.enabled}
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
								{:else}
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636" />
								{/if}
							</svg>
						</button>
						<button
							onclick={() => deleteSchedule(schedule.id)}
							title="Delete"
							class="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-700 hover:text-red-400"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
							</svg>
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Add Cleanup Schedule Modal -->
{#if showForm}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { showForm = false; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-lg rounded-xl bg-gray-900 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between border-b border-gray-800 p-4">
				<h2 class="text-lg font-semibold text-gray-100">{editingId ? 'Edit Cleanup Schedule' : 'Add Cleanup Schedule'}</h2>
				<button onclick={() => { showForm = false; }} class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="space-y-4 p-4">
				<!-- Profile selector -->
				<div>
					<label class="mb-1 block text-sm font-medium text-gray-300">Profile</label>
					<select
						bind:value={formProfileId}
						disabled={!!editingId}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
					>
						{#each profiles as p}
							<option value={p.id}>{p.name}</option>
						{/each}
					</select>
				</div>

				<!-- Name -->
				<div>
					<label class="mb-1 block text-sm font-medium text-gray-300">Name</label>
					<input
						type="text"
						bind:value={formName}
						placeholder="e.g. Daily cleanup"
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

				<!-- Retention settings -->
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">Capture retention (days)</label>
						<input
							type="number"
							bind:value={formCaptureDays}
							min="1"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">Timelapse retention (days)</label>
						<input
							type="number"
							bind:value={formTimelapseDays}
							min="1"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
				</div>

				<!-- Frequency presets -->
				<div>
					<label class="mb-2 block text-sm font-medium text-gray-300">Frequency</label>
					<div class="grid grid-cols-3 gap-2">
						{#each Object.entries(PRESETS) as [key, info]}
							<button
								onclick={() => selectPreset(key)}
								class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors {formPreset === key && !formCustom ? 'border-blue-500 bg-blue-600 text-white' : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'}"
							>
								{info.label}
							</button>
						{/each}
						<button
							onclick={selectCustom}
							class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors {formCustom ? 'border-blue-500 bg-blue-600 text-white' : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'}"
						>
							Custom
						</button>
					</div>
				</div>

				{#if formCustom}
					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">Cron Expression</label>
						<input
							type="text"
							bind:value={formCron}
							placeholder="0 3 * * *"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">Format: minute hour day month weekday</p>
					</div>
				{/if}
			</div>
			<div class="flex justify-end gap-2 border-t border-gray-800 p-4">
				<button
					onclick={() => { showForm = false; }}
					class="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
				>
					Cancel
				</button>
				<button
					onclick={saveSchedule}
					disabled={saving}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{saving ? 'Saving...' : 'Save Schedule'}
				</button>
			</div>
		</div>
	</div>
{/if}
