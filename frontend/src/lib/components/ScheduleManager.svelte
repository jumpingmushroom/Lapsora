<script lang="ts">
	import { api } from '$lib/api';
	import { formatDateTime, formatCronTime } from '$lib/utils';
	import { defaultRenderDraft, renderDraftFromSchedule } from '$lib/renderDraft';
	import type { RenderDraft } from '$lib/renderDraft';
	import type { TimelapseSchedule, Profile, Stream } from '$lib/types';
	import RenderWizard from './RenderWizard.svelte';

	let schedules = $state<TimelapseSchedule[]>([]);
	let profiles = $state<Profile[]>([]);
	let streams = $state<Stream[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// The form is the shared render wizard; this component only decides
	// which draft to open it with.
	let showForm = $state(false);
	let editingId = $state<number | null>(null);
	let formDraft = $state<RenderDraft>(defaultRenderDraft('repeat'));

	// Descriptions stay here (they are list copy); the cron values themselves
	// live in renderDraft.ts so the wizard and this list cannot disagree.
	const PRESETS: Record<string, { label: string; descriptionFn: () => string }> = {
		daily: { label: 'Daily', descriptionFn: () => `Every day at ${formatCronTime(0, 5)}` },
		weekly: { label: 'Weekly', descriptionFn: () => `Sunday at ${formatCronTime(0, 30)}` },
		monthly: { label: 'Monthly', descriptionFn: () => `1st of month at ${formatCronTime(1, 0)}` },
		yearly: { label: 'Yearly', descriptionFn: () => `Jan 1 at ${formatCronTime(2, 0)}` }
	};

	async function load() {
		loading = true;
		error = null;
		try {
			// One profiles call rather than a per-camera fan-out, matching the
			// pattern already used on the dashboard and cameras pages.
			const [s, fetchedStreams, allProfiles] = await Promise.all([
				api.getTimelapseSchedules(),
				api.getStreams(),
				api.getAllProfiles()
			]);
			schedules = s;
			streams = fetchedStreams;
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
		formDraft = defaultRenderDraft('repeat', profiles.length ? profiles[0].id : 0);
		showForm = true;
	}

	function openEdit(schedule: TimelapseSchedule) {
		editingId = schedule.id;
		formDraft = renderDraftFromSchedule(schedule);
		showForm = true;
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
			alert(result.message || 'Render started');
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
		if (!p) return `Plan #${id}`;
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
		return p?.name ?? `Plan #${profileId}`;
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
	let activeProfileFilters = $state<Set<string>>(new Set());
	let activeFreqFilters = $state<Set<string>>(new Set());
	let collapsedStreams = $state<Set<string>>(new Set());

	function toggleStreamFilter(name: string) {
		const next = new Set(activeStreamFilters);
		if (next.has(name)) next.delete(name); else next.add(name);
		activeStreamFilters = next;
	}

	function toggleProfileFilter(name: string) {
		const next = new Set(activeProfileFilters);
		if (next.has(name)) next.delete(name); else next.add(name);
		activeProfileFilters = next;
	}

	function toggleFreqFilter(freq: string) {
		const next = new Set(activeFreqFilters);
		if (next.has(freq)) next.delete(freq); else next.add(freq);
		activeFreqFilters = next;
	}

	function resetFilters() {
		activeStreamFilters = new Set();
		activeProfileFilters = new Set();
		activeFreqFilters = new Set();
	}

	function toggleCollapse(name: string) {
		const next = new Set(collapsedStreams);
		if (next.has(name)) next.delete(name); else next.add(name);
		collapsedStreams = next;
	}

	let uniqueStreams = $derived([...new Set(schedules.map(s => streamName(s.profile_id)))].sort());
	let uniqueProfiles = $derived([...new Set(schedules.map(s => profileOnlyName(s.profile_id)))].sort());
	let uniqueFreqs = $derived([...new Set(schedules.map(s => frequencyLabel(s)))]);

	let groupedSchedules = $derived.by(() => {
		const filtered = schedules.filter(s => {
			if (activeStreamFilters.size > 0 && !activeStreamFilters.has(streamName(s.profile_id))) return false;
			if (activeProfileFilters.size > 0 && !activeProfileFilters.has(profileOnlyName(s.profile_id))) return false;
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

	let hasActiveFilters = $derived(activeStreamFilters.size > 0 || activeProfileFilters.size > 0 || activeFreqFilters.size > 0);
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape' && showForm) showForm = false; }} />

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
		<p class="text-sm text-gray-500">No schedules configured. Add one to render timelapses automatically.</p>
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
			{#each uniqueProfiles as pn}
					<button
						onclick={() => toggleProfileFilter(pn)}
						class="rounded-full px-3 py-1 text-xs font-medium transition-colors {activeProfileFilters.has(pn) ? 'bg-teal-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}"
					>{pn}</button>
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
											{#if schedule.name}
												<span class="text-sm text-gray-400">{schedule.name}</span>
											{/if}
										</div>
										<div class="flex items-center gap-2 shrink-0 ml-3">
											<span class="rounded bg-teal-900/50 px-1.5 py-0.5 text-xs text-teal-300">{profileOnlyName(schedule.profile_id)}</span>
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
											{#if schedule.ha_overlay}
												<span class="rounded bg-sky-900/50 px-1.5 py-0.5 text-sky-300">HA</span>
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

{#if showForm}
	<RenderWizard
		draft={formDraft}
		mode={editingId ? 'edit' : 'create'}
		scheduleId={editingId}
		lockMode="repeat"
		onclose={() => { showForm = false; }}
		ondone={load}
	/>
{/if}
