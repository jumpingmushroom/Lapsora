<script lang="ts">
	import { api } from '$lib/api';
	import { formatDateTime, formatCronTime } from '$lib/utils';
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
	let formFormat = $state('mkv');
	let formDeflicker = $state('medium');
	let formMotionBlur = $state('off');
	let formLookbackHours = $state<number | null>(null);
	let formTimestampOverlay = $state(false);
	let formWeatherOverlay = $state(false);
	let formWeatherPosition = $state('bottom-right');
	let formWeatherFontSize = $state(24);
	let formWeatherUnit = $state('C');
	let formHeatmapOverlay = $state(false);
	let formHeatmapMode = $state('cumulative');
	let formHeatmapColormap = $state('jet');
	let formHeatmapThreshold = $state(10);
	let formCodec = $state('auto');
	let formResolutionPreset = $state('original');
	let formOutputWidth = $state<number | null>(null);
	let formOutputHeight = $state<number | null>(null);
	let formQualityPreset = $state('medium');
	let formCustom = $state(false);
	let saving = $state(false);
	let editingId = $state<number | null>(null);
	let nvencAvailable = $state(false);

	$effect(() => {
		api.getSystemInfo().then((info) => {
			nvencAvailable = info.nvenc_available;
		}).catch(() => {});
	});

	let selectedFormProfile = $derived(profiles.find(p => p.id == formProfileId));
	let formMaxWidth = $derived(selectedFormProfile?.resolution_width ?? Infinity);
	let formMaxHeight = $derived(selectedFormProfile?.resolution_height ?? Infinity);

	// Reset resolution when profile changes and current preset exceeds source
	$effect(() => {
		formProfileId;
		const dims = RESOLUTION_PRESETS[formResolutionPreset];
		if (dims && (dims[0] > formMaxWidth || dims[1] > formMaxHeight)) {
			formResolutionPreset = 'original';
			formOutputWidth = null;
			formOutputHeight = null;
		}
	});

	const RESOLUTION_PRESETS: Record<string, [number, number] | null> = {
		original: null,
		'720p': [1280, 720],
		'1080p': [1920, 1080],
		'4k': [3840, 2160],
		'8k': [7680, 4320]
	};

	function onFormResolutionChange() {
		if (formResolutionPreset === 'custom') {
			formOutputWidth = null;
			formOutputHeight = null;
		} else {
			const dims = RESOLUTION_PRESETS[formResolutionPreset];
			if (dims) {
				formOutputWidth = dims[0];
				formOutputHeight = dims[1];
			} else {
				formOutputWidth = null;
				formOutputHeight = null;
			}
		}
	}

	function detectResolutionPreset(w: number | null, h: number | null): string {
		if (!w || !h) return 'original';
		for (const [key, dims] of Object.entries(RESOLUTION_PRESETS)) {
			if (dims && dims[0] === w && dims[1] === h) return key;
		}
		return 'custom';
	}

	const PRESET_LOOKBACK: Record<string, number> = { daily: 24, weekly: 168, monthly: 730, yearly: 8760 };

	const PRESETS: Record<string, { label: string; cron: string; descriptionFn: () => string }> = {
		daily: { label: 'Daily', cron: '5 0 * * *', descriptionFn: () => `Every day at ${formatCronTime(0, 5)}` },
		weekly: { label: 'Weekly', cron: '30 0 * * 0', descriptionFn: () => `Sunday at ${formatCronTime(0, 30)}` },
		monthly: { label: 'Monthly', cron: '0 1 1 * *', descriptionFn: () => `1st of month at ${formatCronTime(1, 0)}` },
		yearly: { label: 'Yearly', cron: '0 2 1 1 *', descriptionFn: () => `Jan 1 at ${formatCronTime(2, 0)}` }
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
		formFormat = 'mkv';
		formDeflicker = 'medium';
		formMotionBlur = 'off';
		formLookbackHours = null;
		formTimestampOverlay = false;
		formWeatherOverlay = false;
		formWeatherPosition = 'bottom-right';
		formWeatherFontSize = 24;
		formWeatherUnit = 'C';
		formHeatmapOverlay = false;
		formHeatmapMode = 'cumulative';
		formHeatmapColormap = 'jet';
		formHeatmapThreshold = 10;
		formCodec = 'auto';
		formResolutionPreset = 'original';
		formOutputWidth = null;
		formOutputHeight = null;
		formQualityPreset = 'medium';
		formCustom = false;
		showForm = true;
	}

	function openEdit(schedule: TimelapseSchedule) {
		editingId = schedule.id;
		formProfileId = schedule.profile_id;
		formName = schedule.name || '';
		formFps = schedule.fps;
		formFormat = schedule.format;
		formDeflicker = schedule.deflicker || 'medium';
		formMotionBlur = schedule.motion_blur || 'off';
		formLookbackHours = schedule.lookback_hours;
		formTimestampOverlay = schedule.timestamp_overlay;
		formWeatherOverlay = schedule.weather_overlay;
		formWeatherPosition = schedule.weather_position;
		formWeatherFontSize = schedule.weather_font_size;
		formWeatherUnit = schedule.weather_unit;
		formHeatmapOverlay = schedule.heatmap_overlay;
		formHeatmapMode = schedule.heatmap_mode;
		formHeatmapColormap = schedule.heatmap_colormap;
		formHeatmapThreshold = schedule.heatmap_threshold;
		formCodec = schedule.codec || 'auto';
		formOutputWidth = schedule.output_width;
		formOutputHeight = schedule.output_height;
		formResolutionPreset = detectResolutionPreset(schedule.output_width, schedule.output_height);
		formQualityPreset = schedule.quality_preset || 'medium';
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
			const overlayFields = {
				timestamp_overlay: formTimestampOverlay,
				weather_overlay: formWeatherOverlay,
				weather_position: formWeatherPosition,
				weather_font_size: formWeatherFontSize,
				weather_unit: formWeatherUnit,
				heatmap_overlay: formHeatmapOverlay,
				heatmap_mode: formHeatmapMode,
				heatmap_colormap: formHeatmapColormap,
			heatmap_threshold: formHeatmapThreshold,
				motion_blur: formMotionBlur,
				codec: formCodec,
				output_width: formOutputWidth,
				output_height: formOutputHeight,
				quality_preset: formQualityPreset
			};
			if (editingId) {
				await api.updateTimelapseSchedule(editingId, {
					name: formName,
					preset: formPreset,
					cron_expression: formCustom ? formCron : undefined,
					fps: formFps,
					format: formFormat,
					deflicker: formDeflicker,
					lookback_hours: formLookbackHours ?? undefined,
					...overlayFields
				});
			} else {
				await api.createTimelapseSchedule({
					profile_id: formProfileId,
					name: formName,
					preset: formPreset,
					cron_expression: formCustom ? formCron : undefined,
					fps: formFps,
					format: formFormat,
					deflicker: formDeflicker,
					lookback_hours: formLookbackHours ?? undefined,
					...overlayFields
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
			return PRESETS[schedule.preset].descriptionFn();
		}
		return schedule.cron_expression;
	}

	function formatNextRun(iso: string | null): string {
		if (!iso) return 'N/A';
		return formatDateTime(iso);
	}

	function profileName(id: number): string {
		const p = profiles.find((p) => p.id === id);
		if (!p) return `Profile #${id}`;
		const s = streams.find((s) => s.id === p.stream_id);
		return s ? `${s.name} — ${p.name}` : p.name;
	}

	function streamName(profileId: number): string {
		const p = profiles.find((p) => p.id === profileId);
		if (!p) return 'Unknown';
		const s = streams.find((s) => s.id === p.stream_id);
		return s?.name ?? 'Unknown';
	}

	function profileOnlyName(profileId: number): string {
		const p = profiles.find((p) => p.id === profileId);
		return p?.name ?? `Profile #${profileId}`;
	}

	function frequencyLabel(schedule: TimelapseSchedule): string {
		if (schedule.preset && PRESETS[schedule.preset]) return PRESETS[schedule.preset].label;
		return 'Custom';
	}

	const FREQUENCY_ORDER: Record<string, number> = { yearly: 0, monthly: 1, weekly: 2, daily: 3, custom: 4 };
	function frequencySort(s: TimelapseSchedule): number {
		return FREQUENCY_ORDER[s.preset ?? 'custom'] ?? 4;
	}

	// Filter state
	let activeStreamFilters = $state<Set<string>>(new Set());
	let activeFreqFilters = $state<Set<string>>(new Set());
	let collapsedStreams = $state<Set<string>>(new Set());

	function toggleStreamFilter(name: string) {
		const next = new Set(activeStreamFilters);
		if (next.has(name)) next.delete(name); else next.add(name);
		activeStreamFilters = next;
	}

	function toggleFreqFilter(freq: string) {
		const next = new Set(activeFreqFilters);
		if (next.has(freq)) next.delete(freq); else next.add(freq);
		activeFreqFilters = next;
	}

	function resetFilters() {
		activeStreamFilters = new Set();
		activeFreqFilters = new Set();
	}

	function toggleCollapse(name: string) {
		const next = new Set(collapsedStreams);
		if (next.has(name)) next.delete(name); else next.add(name);
		collapsedStreams = next;
	}

	let uniqueStreams = $derived([...new Set(schedules.map(s => streamName(s.profile_id)))].sort());
	let uniqueFreqs = $derived([...new Set(schedules.map(s => frequencyLabel(s)))]);

	let groupedSchedules = $derived.by(() => {
		const filtered = schedules.filter(s => {
			if (activeStreamFilters.size > 0 && !activeStreamFilters.has(streamName(s.profile_id))) return false;
			if (activeFreqFilters.size > 0 && !activeFreqFilters.has(frequencyLabel(s))) return false;
			return true;
		});
		const groups = new Map<string, TimelapseSchedule[]>();
		for (const s of filtered) {
			const sn = streamName(s.profile_id);
			if (!groups.has(sn)) groups.set(sn, []);
			groups.get(sn)!.push(s);
		}
		for (const arr of groups.values()) {
			arr.sort((a, b) => frequencySort(a) - frequencySort(b));
		}
		return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
	});

	let hasActiveFilters = $derived(activeStreamFilters.size > 0 || activeFreqFilters.size > 0);
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
		<!-- Filter chips -->
		<div class="mb-4 flex flex-wrap gap-2">
			<button
				onclick={resetFilters}
				class="rounded-full px-3 py-1 text-xs font-medium transition-colors {hasActiveFilters ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-blue-600 text-white'}"
			>All</button>
			{#each uniqueStreams as sn}
				<button
					onclick={() => toggleStreamFilter(sn)}
					class="rounded-full px-3 py-1 text-xs font-medium transition-colors {activeStreamFilters.has(sn) ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}"
				>{sn}</button>
			{/each}
			<span class="mx-1 self-center text-gray-600">|</span>
			{#each uniqueFreqs as freq}
				<button
					onclick={() => toggleFreqFilter(freq)}
					class="rounded-full px-3 py-1 text-xs font-medium transition-colors {activeFreqFilters.has(freq) ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}"
				>{freq}</button>
			{/each}
		</div>

		<!-- Grouped schedule list -->
		<div class="space-y-4">
			{#each groupedSchedules as [groupName, groupSchedules]}
				<div>
					<button
						onclick={() => toggleCollapse(groupName)}
						class="mb-2 flex w-full items-center gap-2 text-left"
					>
						<svg class="h-4 w-4 text-gray-400 transition-transform {collapsedStreams.has(groupName) ? '' : 'rotate-90'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
						</svg>
						<span class="text-sm font-semibold text-gray-200">{groupName}</span>
						<span class="text-xs text-gray-500">({groupSchedules.length})</span>
					</button>
					{#if !collapsedStreams.has(groupName)}
						<div class="space-y-2 pl-6">
							{#each groupSchedules as schedule}
								<div class="rounded-lg border border-gray-700 bg-gray-800 p-3 {schedule.enabled ? '' : 'opacity-50'}">
									<div class="flex items-center justify-between">
										<div class="flex items-center gap-2 min-w-0">
											<span class="font-medium text-white">{streamName(schedule.profile_id)}</span>
											<span class="text-sm text-gray-400">{schedule.name || profileOnlyName(schedule.profile_id)}</span>
										</div>
										<div class="flex items-center gap-2 shrink-0 ml-3">
											<span class="rounded bg-blue-900/50 px-1.5 py-0.5 text-xs text-blue-300">{frequencyLabel(schedule).toLowerCase()}</span>
											{#if schedule.lookback_hours}
												<span class="rounded bg-purple-900/50 px-1.5 py-0.5 text-xs text-purple-300">{formatLookback(schedule.lookback_hours)}</span>
											{/if}
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
									<div class="mt-1.5 flex items-center justify-between text-xs text-gray-400">
										<div class="flex items-center gap-3">
											<span>{schedule.fps}fps</span>
											<span>{schedule.format.toUpperCase()}</span>
											{#if schedule.timestamp_overlay}
												<span class="rounded bg-gray-700 px-1.5 py-0.5 text-gray-300">Timestamp</span>
											{/if}
											{#if schedule.weather_overlay}
												<span class="rounded bg-sky-900/50 px-1.5 py-0.5 text-sky-300">Weather</span>
											{/if}
											{#if schedule.heatmap_overlay}
												<span class="rounded bg-orange-900/50 px-1.5 py-0.5 text-orange-300">Heatmap</span>
											{/if}
											{#if schedule.motion_blur && schedule.motion_blur !== 'off'}
												<span class="rounded bg-indigo-900/50 px-1.5 py-0.5 text-indigo-300">Blur: {schedule.motion_blur}</span>
											{/if}
										</div>
										<div class="flex items-center gap-3">
											<span>{describeCron(schedule)}</span>
											{#if schedule.next_run}
												<span>Next: {formatNextRun(schedule.next_run)}</span>
											{/if}
										</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
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
		<div class="mx-4 w-full max-w-lg rounded-xl bg-gray-900 shadow-xl max-h-[90vh] flex flex-col" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between border-b border-gray-800 p-4 shrink-0">
				<h2 class="text-lg font-semibold text-gray-100">{editingId ? 'Edit Schedule' : 'Add Schedule'}</h2>
				<button onclick={() => { showForm = false; }} class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="space-y-4 p-4 overflow-y-auto">
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

					<div class="grid grid-cols-3 gap-3">
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
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Deflicker</label>
							<select
								bind:value={formDeflicker}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="off">Off</option>
								<option value="light">Light</option>
								<option value="medium">Medium</option>
								<option value="heavy">Heavy</option>
							</select>
						</div>
					</div>

					{#if formFormat !== 'gif'}
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Motion Blur</label>
							<select
								bind:value={formMotionBlur}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="off">Off</option>
								<option value="low">Low</option>
								<option value="medium">Medium</option>
								<option value="high">High</option>
							</select>
						</div>
					{/if}

					{#if formFormat === 'mp4' || formFormat === 'mkv'}
						<div>
							<label class="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
								Codec
								{#if nvencAvailable}
									<span class="rounded bg-green-900/50 px-1.5 py-0.5 text-xs font-semibold text-green-300">GPU</span>
								{/if}
							</label>
							<select
								bind:value={formCodec}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="auto">Auto</option>
								<option value="h264">H.264</option>
								<option value="h265">H.265 (HEVC)</option>
							</select>
						</div>
					{/if}

					{#if formFormat !== 'gif'}
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Output Resolution</label>
							<select
								bind:value={formResolutionPreset}
								onchange={onFormResolutionChange}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="original">Original</option>
								{#each Object.entries(RESOLUTION_PRESETS) as [key, dims]}
									{#if dims && dims[0] <= formMaxWidth && dims[1] <= formMaxHeight}
										<option value={key}>{key}</option>
									{/if}
								{/each}
								<option value="custom">Custom</option>
							</select>
						</div>

						{#if formResolutionPreset === 'custom'}
							<div class="grid grid-cols-2 gap-3">
								<div>
									<label class="mb-1 block text-sm font-medium text-gray-300">Width</label>
									<input
										type="number"
										bind:value={formOutputWidth}
										min="1"
										max={formMaxWidth === Infinity ? undefined : formMaxWidth}
										placeholder="Width"
										class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
									/>
								</div>
								<div>
									<label class="mb-1 block text-sm font-medium text-gray-300">Height</label>
									<input
										type="number"
										bind:value={formOutputHeight}
										min="1"
										max={formMaxHeight === Infinity ? undefined : formMaxHeight}
										placeholder="Height"
										class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
									/>
								</div>
							</div>
						{/if}

						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Quality</label>
							<select
								bind:value={formQualityPreset}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="low">Low</option>
								<option value="medium">Medium</option>
								<option value="high">High</option>
								<option value="lossless">Lossless</option>
							</select>
						</div>
					{/if}

					<!-- Overlay options -->
					<div class="flex items-center gap-3">
						<input
							id="sched-timestamp"
							type="checkbox"
							bind:checked={formTimestampOverlay}
							class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
						/>
						<label for="sched-timestamp" class="text-sm font-medium text-gray-300">Timestamp overlay</label>
					</div>

					<div class="flex items-center gap-3">
						<input
							id="sched-weather"
							type="checkbox"
							bind:checked={formWeatherOverlay}
							class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
						/>
						<label for="sched-weather" class="text-sm font-medium text-gray-300">Weather overlay</label>
					</div>

					{#if formWeatherOverlay}
						<div class="space-y-3 rounded-md border border-gray-700 bg-gray-800/50 p-3">
							<div>
								<label for="sched-weather-pos" class="mb-1 block text-sm font-medium text-gray-300">Position</label>
								<select
									id="sched-weather-pos"
									bind:value={formWeatherPosition}
									class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								>
									<option value="top-left">Top Left</option>
									<option value="top-right">Top Right</option>
									<option value="bottom-left">Bottom Left</option>
									<option value="bottom-right">Bottom Right</option>
								</select>
							</div>
							<div>
								<label for="sched-weather-size" class="mb-1 block text-sm font-medium text-gray-300">Font size</label>
								<input
									id="sched-weather-size"
									type="number"
									bind:value={formWeatherFontSize}
									min="10"
									max="72"
									class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
							</div>
							<div>
								<label class="mb-1 block text-sm font-medium text-gray-300">Unit</label>
								<div class="flex gap-4">
									<label class="flex items-center gap-2 text-sm text-gray-300">
										<input type="radio" bind:group={formWeatherUnit} value="C" class="text-blue-500" />
										°C
									</label>
									<label class="flex items-center gap-2 text-sm text-gray-300">
										<input type="radio" bind:group={formWeatherUnit} value="F" class="text-blue-500" />
										°F
									</label>
								</div>
							</div>
						</div>
					{/if}

					<div class="flex items-center gap-3">
						<input
							id="sched-heatmap"
							type="checkbox"
							bind:checked={formHeatmapOverlay}
							class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
						/>
						<label for="sched-heatmap" class="text-sm font-medium text-gray-300">Activity heatmap overlay</label>
					</div>

					{#if formHeatmapOverlay}
						<div class="space-y-3 rounded-md border border-gray-700 bg-gray-800/50 p-3">
							<div>
								<label for="sched-heatmap-mode" class="mb-1 block text-sm font-medium text-gray-300">Mode</label>
								<select
									id="sched-heatmap-mode"
									bind:value={formHeatmapMode}
									class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								>
									<option value="cumulative">Cumulative</option>
									<option value="sliding">Sliding window</option>
								</select>
							</div>
							<div>
								<label for="sched-heatmap-threshold" class="mb-1 block text-sm font-medium text-gray-300">Threshold: {formHeatmapThreshold}</label>
								<input
									id="sched-heatmap-threshold"
									type="range"
									bind:value={formHeatmapThreshold}
									min="0"
									max="50"
									step="1"
									class="w-full accent-blue-500"
								/>
								<p class="mt-0.5 text-xs text-gray-500">Filters noise — 0 = most sensitive, 50 = least sensitive</p>
							</div>
							<div>
								<label for="sched-heatmap-colormap" class="mb-1 block text-sm font-medium text-gray-300">Colormap</label>
								<select
									id="sched-heatmap-colormap"
									bind:value={formHeatmapColormap}
									class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								>
									<option value="jet">Jet</option>
									<option value="inferno">Inferno</option>
									<option value="viridis">Viridis</option>
									<option value="turbo">Turbo</option>
								</select>
							</div>
						</div>
					{/if}
				{/if}
			</div>
			{#if formPreset || formCustom}
				<div class="flex justify-end gap-2 border-t border-gray-800 p-4 shrink-0">
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
