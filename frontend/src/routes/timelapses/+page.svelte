<script lang="ts">
	import { api } from '$lib/api';
	import type { Timelapse, Profile, Stream } from '$lib/types';
	import TimelapsePlayer from '$lib/components/TimelapsePlayer.svelte';
	import GenerateDialog from '$lib/components/GenerateDialog.svelte';

	let timelapses = $state<Timelapse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Filters
	let filterPeriod = $state('');
	let filterFormat = $state('');

	// Player modal
	let selectedTimelapse = $state<Timelapse | null>(null);

	// Generate dialog
	let showGenerate = $state(false);
	let allProfiles = $state<Profile[]>([]);
	let generateMsg = $state('');

	async function loadTimelapses() {
		loading = true;
		error = null;
		try {
			timelapses = await api.getTimelapses({
				period_type: filterPeriod || undefined
			});
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadTimelapses();
	});

	// Reload when filters change
	$effect(() => {
		// Access reactive deps
		filterPeriod;
		loadTimelapses();
	});

	let filteredTimelapses = $derived(
		filterFormat
			? timelapses.filter((t) => t.format === filterFormat)
			: timelapses
	);

	async function openGenerate() {
		try {
			const streams = await api.getStreams();
			const profiles: Profile[] = [];
			await Promise.all(
				streams.map(async (s) => {
					const p = await api.getStreamProfiles(s.id);
					profiles.push(...p);
				})
			);
			allProfiles = profiles;
			showGenerate = true;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to load profiles');
		}
	}

	async function handleGenerate(profileId: number, data: Parameters<typeof api.generateTimelapse>[1]) {
		try {
			const result = await api.generateTimelapse(profileId, data);
			showGenerate = false;
			generateMsg = result.message || 'Generation started';
			setTimeout(() => { generateMsg = ''; }, 4000);
			await loadTimelapses();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Generation failed');
		}
	}

	function formatDate(iso: string | null): string {
		if (!iso) return 'N/A';
		return new Date(iso).toLocaleDateString();
	}

	function formatDuration(seconds: number | null): string {
		if (!seconds) return '--';
		const m = Math.floor(seconds / 60);
		const s = Math.round(seconds % 60);
		return m > 0 ? `${m}m ${s}s` : `${s}s`;
	}

	function formatBytes(bytes: number | null): string {
		if (!bytes) return '--';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold text-white">Timelapses</h1>
		<button
			onclick={openGenerate}
			class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			Generate
		</button>
	</div>

	{#if generateMsg}
		<div class="rounded-lg border border-green-800 bg-green-950/50 p-3 text-sm text-green-400">{generateMsg}</div>
	{/if}

	<!-- Filters -->
	<div class="flex flex-wrap gap-3">
		<select
			bind:value={filterPeriod}
			class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		>
			<option value="">All periods</option>
			<option value="daily">Daily</option>
			<option value="weekly">Weekly</option>
			<option value="monthly">Monthly</option>
			<option value="yearly">Yearly</option>
			<option value="custom">Custom</option>
		</select>
		<select
			bind:value={filterFormat}
			class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		>
			<option value="">All formats</option>
			<option value="mp4">MP4</option>
			<option value="webm">WebM</option>
			<option value="gif">GIF</option>
		</select>
	</div>

	{#if loading}
		<p class="text-gray-400">Loading timelapses...</p>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
			<p class="text-sm text-red-400">{error}</p>
		</div>
	{:else if filteredTimelapses.length === 0}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center">
			<p class="text-gray-400">No timelapses found.</p>
			<p class="mt-1 text-sm text-gray-500">Generate a timelapse from your captured frames.</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each filteredTimelapses as tl}
				<div class="rounded-xl border border-gray-800 bg-gray-900 p-4 transition-colors hover:border-gray-700">
					<!-- Thumbnail / click to play -->
					<button
						onclick={() => { selectedTimelapse = tl; }}
						class="mb-3 flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg bg-gray-800 text-gray-500 hover:text-gray-300"
					>
						<svg class="h-12 w-12" fill="currentColor" viewBox="0 0 24 24">
							<path d="M8 5v14l11-7z" />
						</svg>
					</button>

					<div class="mb-2 flex items-center gap-2">
						<span class="rounded bg-purple-900 px-2 py-0.5 text-xs font-medium text-purple-300">{tl.format.toUpperCase()}</span>
						{#if tl.period_type}
							<span class="text-xs text-gray-400">{tl.period_type}</span>
						{/if}
					</div>

					<div class="mb-3 text-xs text-gray-500">
						{formatDate(tl.period_start)} - {formatDate(tl.period_end)}
					</div>

					<div class="mb-3 grid grid-cols-3 gap-2 text-xs text-gray-400">
						<div>
							<span class="text-gray-600">Duration</span>
							<p class="text-gray-300">{formatDuration(tl.duration_seconds)}</p>
						</div>
						<div>
							<span class="text-gray-600">Frames</span>
							<p class="text-gray-300">{tl.frame_count ?? '--'}</p>
						</div>
						<div>
							<span class="text-gray-600">Size</span>
							<p class="text-gray-300">{formatBytes(tl.file_size)}</p>
						</div>
					</div>

					<a
						href={api.getTimelapseVideoUrl(tl.id)}
						download
						class="inline-flex items-center rounded px-3 py-1.5 text-xs font-medium text-blue-400 transition-colors hover:bg-gray-800"
					>
						<svg class="mr-1 h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
						Download
					</a>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Player Modal -->
{#if selectedTimelapse}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { selectedTimelapse = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-3xl rounded-xl bg-gray-900 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between border-b border-gray-800 p-4">
				<h2 class="text-lg font-semibold text-gray-100">Timelapse Player</h2>
				<button onclick={() => { selectedTimelapse = null; }} class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="p-4">
				<TimelapsePlayer timelapse={selectedTimelapse} />
			</div>
		</div>
	</div>
{/if}

<!-- Generate Dialog -->
{#if showGenerate}
	<GenerateDialog
		profileId={allProfiles.length > 0 ? allProfiles[0].id : 0}
		open={true}
		onclose={() => { showGenerate = false; }}
	/>
{/if}
