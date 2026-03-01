<script lang="ts">
	import { api } from '$lib/api';
	import type { TimelapseSchedule, Profile, Stream } from '$lib/types';

	let schedules = $state<TimelapseSchedule[]>([]);
	let profiles = $state<Profile[]>([]);
	let streams = $state<Stream[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Add form state
	let showForm = $state(false);
	let formProfileId = $state<number | null>(null);
	let formPreset = $state<string | null>(null);
	let formCron = $state('');
	let formName = $state('');
	let formFps = $state(24);
	let formFormat = $state('mp4');
	let formLookbackHours = $state<number | null>(null);
	let formCustom = $state(false);
	let saving = $state(false);
	let editingId = $state<number | null>(null);

	const PRESET_LOOKBACK: Record<string, number> = { daily: 24, weekly: 168, monthly: 730, yearly: 8760 };

	const PRESETS: Record<string, { label: string; cron: string; description: string }> = {
		daily: { label: 'Daily', cron: '5 0 * * *', description: 'Every day at 00:05' },
		weekly: { label: 'Weekly', cron: '30 0 * * 0', description: 'Sunday at 00:30' },
		monthly: { label: 'Monthly', cron: '0 1 1 * *', description: '1st of month at 01:00' },
		yearly: { label: 'Yearly', cron: '0 2 1 1 *', description: 'Jan 1 at 02:00' }
	};

	async function load() {
		loading = true;
		error = null;
		try {
			const [s, fetchedStreams] = await Promise.all([
				api.getTimelapseSchedules(),
				api.getStreams()
			]);
			schedules = s;
			streams = fetchedStreams;
			const allProfiles: Profile[] = [];
			await Promise.all(
				fetchedStreams.map(async (st) => {
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
		formPreset = null;
		formCron = '';
		formName = '';
		formFps = 24;
		formFormat = 'mp4';
		formLookbackHours = null;
		formCustom = false;
		showForm = true;
	}

	function openEdit(schedule: TimelapseSchedule) {
		editingId = schedule.id;
		formProfileId = schedule.profile_id;
		formName = schedule.name || '';
		formFps = schedule.fps;
		formFormat = schedule.format;
		formLookbackHours = schedule.lookback_hours;
		if (schedule.preset && PRESETS[schedule.preset]) {
			formPreset = schedule.preset;
			formCron = PRESETS[schedule.preset].cron;
			formCustom = false;
		} else {
			formPreset = null;
			formCron = schedule.cron_expression;
			formCustom = true;
		}
		showForm = true;
	}

	function selectPreset(key: string) {
		formPreset = key;
		formCron = PRESETS[key].cron;
		formName = PRESETS[key].label;
		formLookbackHours = PRESET_LOOKBACK[key] ?? null;
		formCustom = false;
	}

	function selectCustom() {
		formPreset = null;
		formCron = '';
		formName = 'Custom';
		formLookbackHours = null;
		formCustom = true;
	}

	async function saveSchedule() {
		if (!formProfileId) return;
		if (!formPreset && !formCron) {
			alert('Please select a preset or enter a cron expression');
			return;
		}
		saving = true;
		try {
			if (editingId) {
				await api.updateTimelapseSchedule(editingId, {
					name: formName,
					preset: formPreset,
					cron_expression: formCustom ? formCron : undefined,
					fps: formFps,
					format: formFormat,
					lookback_hours: formLookbackHours ?? undefined
				});
			} else {
				await api.createTimelapseSchedule({
					profile_id: formProfileId,
					name: formName,
					preset: formPreset,
					cron_expression: formCustom ? formCron : undefined,
					fps: formFps,
					format: formFormat,
					lookback_hours: formLookbackHours ?? undefined
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

	async function toggleEnabled(schedule: TimelapseSchedule) {
		try {
			await api.updateTimelapseSchedule(schedule.id, { enabled: !schedule.enabled });
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update');
		}
	}

	async function deleteSchedule(id: number) {
		if (!confirm('Delete this schedule?')) return;
		try {
			await api.deleteTimelapseSchedule(id);
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete');
		}
	}

	async function triggerNow(id: number) {
		try {
			const result = await api.triggerTimelapseSchedule(id);
			alert(result.message || 'Generation triggered');
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to trigger');
		}
	}

	function formatLookback(hours: number | null): string {
		if (hours === null) return '';
		if (hours < 24) return `Last ${hours}h`;
		if (hours < 168) return `Last ${Math.round(hours / 24)}d`;
		if (hours < 730) return `Last ${Math.round(hours / 168)}w`;
		return `Last ${Math.round(hours / 730)}mo`;
	}

	function describeCron(schedule: TimelapseSchedule): string {
		if (schedule.preset && PRESETS[schedule.preset]) {
			return PRESETS[schedule.preset].description;
		}
		return schedule.cron_expression;
	}

	function formatNextRun(iso: string | null): string {
		if (!iso) return 'N/A';
		return new Date(iso).toLocaleString();
	}

	function profileName(id: number): string {
		const p = profiles.find((p) => p.id === id);
		if (!p) return `Profile #${id}`;
		const s = streams.find((s) => s.id === p.stream_id);
		return s ? `${s.name} — ${p.name}` : p.name;
	}
</script>

<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
	<div class="mb-4 flex items-center justify-between">
		<h2 class="text-lg font-semibold text-white">Schedules</h2>
		<button
			onclick={openForm}
			class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			Add Schedule
		</button>
	</div>

	{#if loading}
		<p class="text-sm text-gray-400">Loading schedules...</p>
	{:else if error}
		<p class="text-sm text-red-400">{error}</p>
	{:else if schedules.length === 0}
		<p class="text-sm text-gray-500">No schedules configured. Add one to automate timelapse generation.</p>
	{:else}
		<div class="space-y-3">
			{#each schedules as schedule}
				<div class="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 p-3">
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span class="font-medium text-gray-100">{schedule.name || (schedule.preset ? PRESETS[schedule.preset]?.label : 'Custom')}</span>
							{#if schedule.preset}
								<span class="rounded bg-blue-900/50 px-1.5 py-0.5 text-xs text-blue-300">{schedule.preset}</span>
							{/if}
							<span class="text-xs text-gray-500">{profileName(schedule.profile_id)}</span>
						</div>
						<div class="mt-1 flex items-center gap-3 text-xs text-gray-400">
							<span>{describeCron(schedule)}</span>
							{#if schedule.lookback_hours}
								<span class="rounded bg-purple-900/50 px-1.5 py-0.5 text-purple-300">{formatLookback(schedule.lookback_hours)}</span>
							{/if}
							<span>{schedule.fps}fps</span>
							<span>{schedule.format.toUpperCase()}</span>
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

<!-- Add Schedule Modal -->
{#if showForm}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { showForm = false; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-lg rounded-xl bg-gray-900 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between border-b border-gray-800 p-4">
				<h2 class="text-lg font-semibold text-gray-100">{editingId ? 'Edit Schedule' : 'Add Schedule'}</h2>
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
						{#each streams as stream}
							<optgroup label={stream.name}>
								{#each profiles.filter(p => p.stream_id === stream.id) as p}
									<option value={p.id}>{p.name}</option>
								{/each}
							</optgroup>
						{/each}
					</select>
				</div>

				<!-- Preset buttons -->
				<div>
					<label class="mb-2 block text-sm font-medium text-gray-300">Schedule Type</label>
					<div class="grid grid-cols-5 gap-2">
						{#each Object.entries(PRESETS) as [key, info]}
							<button
								onclick={() => selectPreset(key)}
								class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors {formPreset === key ? 'border-blue-500 bg-blue-600 text-white' : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'}"
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
							placeholder="*/5 * * * *"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">Format: minute hour day month weekday</p>
					</div>
				{/if}

				{#if formPreset || formCustom}
					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">Lookback Window (hours)</label>
						<input
							type="number"
							bind:value={formLookbackHours}
							min="1"
							placeholder={formPreset ? String(PRESET_LOOKBACK[formPreset] ?? '') : 'e.g. 1 for hourly'}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">
							{#if formLookbackHours}
								Captures from the last {formLookbackHours}h ({formLookbackHours >= 24 ? `${Math.round(formLookbackHours / 24)} days` : `${formLookbackHours} hours`})
							{:else}
								How far back to include captures
							{/if}
						</p>
					</div>

					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">Name</label>
						<input
							type="text"
							bind:value={formName}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">FPS</label>
							<input
								type="number"
								bind:value={formFps}
								min="1"
								max="60"
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							/>
						</div>
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Format</label>
							<select
								bind:value={formFormat}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="mp4">MP4</option>
								<option value="webm">WebM</option>
								<option value="gif">GIF</option>
								<option value="mkv">MKV</option>
							</select>
						</div>
					</div>
				{/if}
			</div>
			{#if formPreset || formCustom}
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
			{/if}
		</div>
	</div>
{/if}
