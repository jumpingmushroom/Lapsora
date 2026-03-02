<script lang="ts">
	import { api } from '$lib/api';
	import type { Timelapse } from '$lib/types';
	import { formatDate, formatDuration, formatBytes } from '$lib/utils';
	import TimelapsePlayer from '$lib/components/TimelapsePlayer.svelte';
	import GenerateDialog from '$lib/components/GenerateDialog.svelte';
	import ScheduleManager from '$lib/components/ScheduleManager.svelte';

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
	let allProfileOptions = $state<{ id: number; label: string }[]>([]);

	// Generation progress
	let generating = $state(0);

	// Delete
	let deleteTarget = $state<Timelapse | null>(null);
	let deleting = $state(false);

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

	// Load on mount and reload when filters change
	$effect(() => {
		filterPeriod;
		loadTimelapses();
	});

	// Listen for timelapse events from layout SSE via CustomEvent
	$effect(() => {
		function handleNotification(e: Event) {
			const data = (e as CustomEvent).detail;
			if (data.event_type === 'timelapse_started') {
				generating = Math.max(0, generating) + 1;
			} else if (data.event_type === 'timelapse_complete') {
				generating = Math.max(0, generating - 1);
				loadTimelapses();
			} else if (data.event_type === 'timelapse_failure') {
				generating = Math.max(0, generating - 1);
			}
		}
		window.addEventListener('lapsora:notification', handleNotification);
		return () => window.removeEventListener('lapsora:notification', handleNotification);
	});

	let filteredTimelapses = $derived(
		filterFormat
			? timelapses.filter((t) => t.format === filterFormat)
			: timelapses
	);

	async function openGenerate() {
		try {
			const streams = await api.getStreams();
			const options: { id: number; label: string }[] = [];
			await Promise.all(
				streams.map(async (s) => {
					const profiles = await api.getStreamProfiles(s.id);
					for (const p of profiles) {
						options.push({ id: p.id, label: `${s.name} — ${p.name}` });
					}
				})
			);
			allProfileOptions = options;
			showGenerate = true;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to load profiles');
		}
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			await api.deleteTimelapse(deleteTarget.id);
			timelapses = timelapses.filter((t) => t.id !== deleteTarget!.id);
			deleteTarget = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Delete failed');
		} finally {
			deleting = false;
		}
	}

</script>

<svelte:head><title>Timelapses - Lapsora</title></svelte:head>

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

	<ScheduleManager />

	{#if generating > 0}
		<div class="rounded-lg border border-blue-800 bg-blue-950/50 p-3">
			<div class="mb-2 flex items-center gap-2 text-sm text-blue-400">
				<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
				</svg>
				Generating timelapse{generating > 1 ? `s (${generating})` : ''}...
			</div>
			<div class="h-1 overflow-hidden rounded-full bg-blue-900">
				<div class="h-full w-1/3 animate-pulse rounded-full bg-blue-500" style="animation: slide 1.5s ease-in-out infinite;"></div>
			</div>
		</div>
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
			<option value="mkv">MKV</option>
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

					<div class="flex items-center gap-1">
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
						<button
							onclick={() => { deleteTarget = tl; }}
							class="inline-flex items-center rounded px-3 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-gray-800"
						>
							<svg class="mr-1 h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
							</svg>
							Delete
						</button>
					</div>
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
		profileOptions={allProfileOptions}
		open={true}
		onclose={() => { showGenerate = false; }}
	/>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { deleteTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-semibold text-gray-100">Confirm Delete</h3>
			<p class="mb-4 text-sm text-gray-400">Are you sure you want to delete this timelapse? This cannot be undone.</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { deleteTarget = null; }}
					class="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-600"
				>
					Cancel
				</button>
				<button
					onclick={confirmDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	@keyframes slide {
		0% { transform: translateX(-100%); }
		50% { transform: translateX(200%); }
		100% { transform: translateX(-100%); }
	}
</style>
