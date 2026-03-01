<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream, Profile, Capture, Timelapse } from '$lib/types';
	import TimelapsePlayer from '$lib/components/TimelapsePlayer.svelte';

	let streams = $state<Stream[]>([]);
	let selectedStreamId = $state<number | null>(null);
	let selectedProfileId = $state<number | null>(null);
	let profiles = $state<Profile[]>([]);
	let captures = $state<Capture[]>([]);
	let timelapses = $state<Timelapse[]>([]);
	let loading = $state(true);
	let loadingMedia = $state(false);

	// Pagination
	let capturePage = $state(0);
	const capturePageSize = 24;
	let hasMoreCaptures = $state(false);

	// Lightbox
	let lightboxCapture = $state<Capture | null>(null);

	// Player
	let selectedTimelapse = $state<Timelapse | null>(null);

	// Delete confirmation
	let deleteTarget = $state<{ type: 'capture' | 'timelapse'; id: number } | null>(null);
	let bulkDeleteTarget = $state<{ type: 'captures' | 'timelapses'; ids: number[] } | null>(null);
	let deleting = $state(false);

	// Selection state — use plain objects for Svelte 5 reactivity
	let selectedCaptures: Record<number, true> = $state({});
	let selectedTimelapses: Record<number, true> = $state({});
	let lastClickedCaptureIdx = $state<number | null>(null);
	let lastClickedTimelapseIdx = $state<number | null>(null);
	let selectedCaptureIds = $derived(Object.keys(selectedCaptures).map(Number));
	let selectedTimelapseIds = $derived(Object.keys(selectedTimelapses).map(Number));
	let selectionCount = $derived(selectedCaptureIds.length + selectedTimelapseIds.length);

	function clearSelection() {
		selectedCaptures = {};
		selectedTimelapses = {};
		lastClickedCaptureIdx = null;
		lastClickedTimelapseIdx = null;
	}

	function toggleCaptureSelection(idx: number, e: MouseEvent) {
		const id = captures[idx].id;
		const next = { ...selectedCaptures };
		if (e.shiftKey && lastClickedCaptureIdx !== null) {
			const start = Math.min(lastClickedCaptureIdx, idx);
			const end = Math.max(lastClickedCaptureIdx, idx);
			for (let i = start; i <= end; i++) {
				next[captures[i].id] = true;
			}
		} else {
			if (next[id]) delete next[id];
			else next[id] = true;
		}
		selectedCaptures = next;
		lastClickedCaptureIdx = idx;
	}

	function toggleTimelapseSelection(idx: number, e: MouseEvent) {
		const id = timelapses[idx].id;
		const next = { ...selectedTimelapses };
		if (e.shiftKey && lastClickedTimelapseIdx !== null) {
			const start = Math.min(lastClickedTimelapseIdx, idx);
			const end = Math.max(lastClickedTimelapseIdx, idx);
			for (let i = start; i <= end; i++) {
				next[timelapses[i].id] = true;
			}
		} else {
			if (next[id]) delete next[id];
			else next[id] = true;
		}
		selectedTimelapses = next;
		lastClickedTimelapseIdx = idx;
	}

	function promptBulkDelete() {
		if (selectedCaptureIds.length > 0 || selectedTimelapseIds.length > 0) {
			bulkDeleteTarget = { type: 'captures', ids: selectedCaptureIds };
		}
	}

	async function confirmBulkDelete() {
		if (!bulkDeleteTarget) return;
		deleting = true;
		try {
			if (selectedCaptureIds.length > 0) {
				await api.bulkDeleteCaptures(selectedCaptureIds);
				captures = captures.filter((c) => !selectedCaptures[c.id]);
			}
			if (selectedTimelapseIds.length > 0) {
				await api.bulkDeleteTimelapses(selectedTimelapseIds);
				timelapses = timelapses.filter((t) => !selectedTimelapses[t.id]);
			}
			clearSelection();
		} catch {
		} finally {
			deleting = false;
			bulkDeleteTarget = null;
		}
	}

	function formatDate(iso: string | null): string {
		if (!iso) return 'N/A';
		return new Date(iso).toLocaleDateString();
	}

	function formatDateTime(iso: string): string {
		return new Date(iso).toLocaleString();
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

	$effect(() => {
		api.getStreams().then((s) => {
			streams = s;
			loading = false;
		}).catch(() => { loading = false; });
	});

	async function selectStream(id: number) {
		selectedStreamId = id;
		selectedProfileId = null;
		loadingMedia = true;
		capturePage = 0;
		captures = [];
		timelapses = [];
		clearSelection();
		try {
			profiles = await api.getStreamProfiles(id);
			await loadCaptures();
			await loadTimelapses();
		} catch {
		} finally {
			loadingMedia = false;
		}
	}

	async function selectProfile(profileId: number | null) {
		selectedProfileId = profileId;
		capturePage = 0;
		loadingMedia = true;
		clearSelection();
		try {
			await loadCaptures();
			await loadTimelapses();
		} catch {
		} finally {
			loadingMedia = false;
		}
	}

	async function loadCaptures() {
		const targetProfiles = selectedProfileId !== null
			? profiles.filter((p) => p.id === selectedProfileId)
			: profiles;
		const allCaptures: Capture[] = [];
		for (const p of targetProfiles) {
			const c = await api.getProfileCaptures(p.id, capturePageSize + 1, capturePage * capturePageSize);
			allCaptures.push(...c);
		}
		allCaptures.sort((a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime());
		hasMoreCaptures = allCaptures.length > capturePageSize;
		captures = allCaptures.slice(0, capturePageSize);
	}

	async function loadTimelapses() {
		const targetProfiles = selectedProfileId !== null
			? profiles.filter((p) => p.id === selectedProfileId)
			: profiles;
		const allTimelapses: Timelapse[] = [];
		for (const p of targetProfiles) {
			const t = await api.getTimelapses({ profile_id: p.id });
			allTimelapses.push(...t);
		}
		allTimelapses.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
		timelapses = allTimelapses;
	}

	async function changePage(delta: number) {
		capturePage += delta;
		loadingMedia = true;
		await loadCaptures();
		loadingMedia = false;
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			if (deleteTarget.type === 'capture') {
				await api.deleteCapture(deleteTarget.id);
				captures = captures.filter((c) => c.id !== deleteTarget!.id);
			} else {
				await api.deleteTimelapse(deleteTarget.id);
				timelapses = timelapses.filter((t) => t.id !== deleteTarget!.id);
			}
		} catch {
		} finally {
			deleting = false;
			deleteTarget = null;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && selectionCount > 0) {
			clearSelection();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="space-y-6">
	<h1 class="text-3xl font-bold text-white">Files</h1>

	<!-- Stream Selector -->
	<div>
		<select
			onchange={(e) => {
				const val = (e.target as HTMLSelectElement).value;
				if (val) selectStream(Number(val));
			}}
			class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		>
			<option value="">Select a stream...</option>
			{#each streams as stream}
				<option value={stream.id} selected={stream.id === selectedStreamId}>{stream.name}</option>
			{/each}
		</select>
	</div>

	{#if selectedStreamId && profiles.length > 1}
		<div class="flex flex-wrap gap-2">
			<button
				onclick={() => selectProfile(null)}
				class="rounded-full px-3 py-1 text-sm transition-colors {selectedProfileId === null ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}"
			>
				All
			</button>
			{#each profiles as profile}
				<button
					onclick={() => selectProfile(profile.id)}
					class="rounded-full px-3 py-1 text-sm transition-colors {selectedProfileId === profile.id ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}"
				>
					{profile.name}
				</button>
			{/each}
		</div>
	{/if}

	{#if loading}
		<p class="text-gray-400">Loading streams...</p>
	{:else if !selectedStreamId}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center">
			<p class="text-gray-400">Select a stream to browse its files.</p>
		</div>
	{:else if loadingMedia}
		<p class="text-gray-400">Loading files...</p>
	{:else}
		<!-- Snapshots -->
		<section>
			<h2 class="mb-4 text-xl font-semibold text-white">Snapshots</h2>
			{#if captures.length === 0}
				<div class="rounded-xl border border-gray-800 bg-gray-900 p-6 text-center">
					<p class="text-gray-400">No snapshots found for this stream.</p>
				</div>
			{:else}
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
					{#each captures as capture, idx}
						<div class="group relative overflow-hidden rounded-lg border bg-gray-900 transition-colors {selectedCaptures[capture.id] ? 'border-blue-500 ring-2 ring-blue-500/40' : 'border-gray-800'}">
							<button
								onclick={() => { lightboxCapture = capture; }}
								class="block w-full"
							>
								<img
									src={api.getCaptureImageUrl(capture.id)}
									alt="Capture {capture.id}"
									class="aspect-video w-full object-cover transition-transform group-hover:scale-105"
									loading="lazy"
								/>
								<div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-2 py-1">
									<span class="text-xs text-gray-300">{formatDateTime(capture.captured_at)}</span>
								</div>
							</button>
							<!-- Selection checkbox -->
							<button
								onclick={(e) => { e.stopPropagation(); toggleCaptureSelection(idx, e); }}
								class="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded transition-opacity {selectionCount > 0 || selectedCaptures[capture.id] ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} {selectedCaptures[capture.id] ? 'bg-blue-500 text-white' : 'bg-black/60 text-gray-400 hover:text-white'}"
								title="Select"
							>
								{#if selectedCaptures[capture.id]}
									<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
									</svg>
								{/if}
							</button>
							<button
								onclick={() => { deleteTarget = { type: 'capture', id: capture.id }; }}
								class="absolute right-1 top-1 rounded bg-black/60 p-1 text-gray-400 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
								title="Delete"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
							</button>
						</div>
					{/each}
				</div>

				<!-- Pagination -->
				<div class="mt-4 flex items-center gap-3">
					{#if capturePage > 0}
						<button onclick={() => changePage(-1)} class="rounded-lg bg-gray-800 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700">Previous</button>
					{/if}
					<span class="text-sm text-gray-500">Page {capturePage + 1}</span>
					{#if hasMoreCaptures}
						<button onclick={() => changePage(1)} class="rounded-lg bg-gray-800 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700">Next</button>
					{/if}
				</div>
			{/if}
		</section>

		<!-- Videos -->
		<section>
			<h2 class="mb-4 text-xl font-semibold text-white">Videos</h2>
			{#if timelapses.length === 0}
				<div class="rounded-xl border border-gray-800 bg-gray-900 p-6 text-center">
					<p class="text-gray-400">No timelapse videos found for this stream.</p>
				</div>
			{:else}
				<div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
					{#each timelapses as tl, idx}
						<div class="relative rounded-xl border bg-gray-900 p-4 transition-colors {selectedTimelapses[tl.id] ? 'border-blue-500 ring-2 ring-blue-500/40' : 'border-gray-800 hover:border-gray-700'}">
							<!-- Selection checkbox -->
							<button
								onclick={(e) => { e.stopPropagation(); toggleTimelapseSelection(idx, e); }}
								class="absolute left-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded transition-opacity {selectionCount > 0 || selectedTimelapses[tl.id] ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} {selectedTimelapses[tl.id] ? 'bg-blue-500 text-white' : 'bg-black/60 text-gray-400 hover:text-white'}"
								title="Select"
							>
								{#if selectedTimelapses[tl.id]}
									<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
									</svg>
								{/if}
							</button>

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

							<div class="flex items-center gap-2">
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
									onclick={() => { deleteTarget = { type: 'timelapse', id: tl.id }; }}
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
		</section>
	{/if}
</div>

<!-- Floating Selection Action Bar -->
{#if selectionCount > 0}
	<div class="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-4 rounded-xl border border-gray-700 bg-gray-900 px-5 py-3 shadow-2xl">
		<span class="text-sm font-medium text-gray-200">
			{selectionCount} selected
		</span>
		<button
			onclick={clearSelection}
			class="rounded-lg px-3 py-1.5 text-sm text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
		>
			Clear
		</button>
		<button
			onclick={promptBulkDelete}
			class="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-red-500"
		>
			Delete Selected
		</button>
	</div>
{/if}

<!-- Lightbox -->
{#if lightboxCapture}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onclick={() => { lightboxCapture = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="relative max-h-[90vh] max-w-[90vw]" onclick={(e) => e.stopPropagation()}>
			<img
				src={api.getCaptureImageUrl(lightboxCapture.id)}
				alt="Capture {lightboxCapture.id}"
				class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
			/>
			<div class="absolute bottom-4 left-4 rounded bg-black/70 px-3 py-1 text-sm text-gray-200">
				{formatDateTime(lightboxCapture.captured_at)}
			</div>
			<button
				onclick={() => { lightboxCapture = null; }}
				class="absolute right-2 top-2 rounded-full bg-black/60 p-2 text-gray-300 hover:text-white"
			>
				<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>
	</div>
{/if}

<!-- Timelapse Player Modal -->
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

<!-- Delete Confirmation (single item) -->
{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { deleteTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-semibold text-white">Confirm Delete</h3>
			<p class="mb-4 text-sm text-gray-400">
				Are you sure you want to delete this {deleteTarget.type}? This cannot be undone.
			</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { deleteTarget = null; }}
					class="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"
				>
					Cancel
				</button>
				<button
					onclick={confirmDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Bulk Delete Confirmation -->
{#if bulkDeleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { bulkDeleteTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-semibold text-white">Confirm Bulk Delete</h3>
			<p class="mb-4 text-sm text-gray-400">
				Are you sure you want to delete {selectionCount} item{selectionCount !== 1 ? 's' : ''}?
				{#if selectedCaptureIds.length > 0}
					{selectedCaptureIds.length} snapshot{selectedCaptureIds.length !== 1 ? 's' : ''}
				{/if}
				{#if selectedCaptureIds.length > 0 && selectedTimelapseIds.length > 0}
					and
				{/if}
				{#if selectedTimelapseIds.length > 0}
					{selectedTimelapseIds.length} video{selectedTimelapseIds.length !== 1 ? 's' : ''}
				{/if}
				will be permanently deleted.
			</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { bulkDeleteTarget = null; }}
					class="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"
				>
					Cancel
				</button>
				<button
					onclick={confirmBulkDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : `Delete ${selectionCount}`}
				</button>
			</div>
		</div>
	</div>
{/if}
