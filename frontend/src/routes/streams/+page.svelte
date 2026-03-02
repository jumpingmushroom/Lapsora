<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream, TestResult, Go2rtcStreamInfo } from '$lib/types';
	import StreamCard from '$lib/components/StreamCard.svelte';

	let streams = $state<Stream[]>([]);
	let profileCounts = $state<Record<number, number>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Add stream modal
	let showAddModal = $state(false);
	let newName = $state('');
	let newUrl = $state('');
	let addLoading = $state(false);
	let addError = $state('');
	let addSourceType = $state<'rtsp' | 'go2rtc'>('rtsp');
	let go2rtcStreams = $state<Go2rtcStreamInfo[]>([]);
	let go2rtcLoading = $state(false);
	let go2rtcError = $state('');
	let selectedGo2rtcName = $state('');

	// Delete confirmation
	let deleteTarget = $state<Stream | null>(null);
	let deleteLoading = $state(false);

	// Test connection
	let testResults = $state<Record<number, { loading: boolean; result?: TestResult }>>({});

	async function loadStreams() {
		try {
			const data = await api.getStreams();
			streams = data;
			const counts: Record<number, number> = {};
			await Promise.all(
				data.map(async (s) => {
					try {
						const profiles = await api.getStreamProfiles(s.id);
						counts[s.id] = profiles.length;
					} catch {
						counts[s.id] = 0;
					}
				})
			);
			profileCounts = counts;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadStreams();
	});

	async function handleAdd(e: SubmitEvent) {
		e.preventDefault();
		addLoading = true;
		addError = '';
		try {
			if (addSourceType === 'go2rtc') {
				await api.createStream({ name: newName, source_type: 'go2rtc', go2rtc_name: selectedGo2rtcName });
			} else {
				await api.createStream({ name: newName, url: newUrl });
			}
			showAddModal = false;
			newName = '';
			newUrl = '';
			selectedGo2rtcName = '';
			loading = true;
			await loadStreams();
		} catch (err) {
			addError = err instanceof Error ? err.message : 'Failed to create stream';
		} finally {
			addLoading = false;
		}
	}

	async function loadGo2rtcStreams() {
		go2rtcLoading = true;
		go2rtcError = '';
		try {
			go2rtcStreams = await api.discoverGo2rtcStreams();
		} catch (err) {
			go2rtcError = err instanceof Error ? err.message : 'Failed to discover streams';
			go2rtcStreams = [];
		} finally {
			go2rtcLoading = false;
		}
	}

	async function handleDelete() {
		if (!deleteTarget) return;
		deleteLoading = true;
		try {
			await api.deleteStream(deleteTarget.id);
			deleteTarget = null;
			loading = true;
			await loadStreams();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to delete';
		} finally {
			deleteLoading = false;
		}
	}

	async function testConnection(id: number) {
		testResults = { ...testResults, [id]: { loading: true } };
		try {
			const result = await api.testStream(id);
			testResults = { ...testResults, [id]: { loading: false, result } };
		} catch (err) {
			testResults = { ...testResults, [id]: { loading: false, result: { success: false, message: err instanceof Error ? err.message : 'Test failed' } } };
		}
	}
</script>

<svelte:head><title>Streams - Lapsora</title></svelte:head>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold text-white">Streams</h1>
		<button
			onclick={() => { showAddModal = true; }}
			class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			Add Stream
		</button>
	</div>

	{#if loading}
		<p class="text-gray-400">Loading streams...</p>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
			<p class="text-sm text-red-400">Failed to load streams: {error}</p>
		</div>
	{:else if streams.length === 0}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center">
			<p class="text-gray-400">No streams configured yet.</p>
			<p class="mt-1 text-sm text-gray-500">Add an RTSP stream to get started.</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each streams as stream}
				<div class="relative">
					<StreamCard {stream} profileCount={profileCounts[stream.id] ?? 0} />
					<div class="mt-2 flex gap-2">
						<button
							onclick={() => testConnection(stream.id)}
							disabled={testResults[stream.id]?.loading}
							class="rounded px-3 py-1 text-xs font-medium text-blue-400 transition-colors hover:bg-gray-800 disabled:opacity-50"
						>
							{testResults[stream.id]?.loading ? 'Testing...' : 'Test Connection'}
						</button>
						<button
							onclick={() => { deleteTarget = stream; }}
							class="rounded px-3 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-gray-800"
						>
							Delete
						</button>
					</div>
					{#if testResults[stream.id]?.result}
						{@const r = testResults[stream.id].result}
						<div class="mt-1 rounded px-3 py-1 text-xs {r?.success ? 'bg-green-950 text-green-400' : 'bg-red-950 text-red-400'}">
							{r?.message}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Add Stream Modal -->
{#if showAddModal}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={() => { showAddModal = false; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-md rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-4 text-lg font-semibold text-gray-100">Add Stream</h2>

			<!-- Source type tabs -->
			<div class="mb-4 flex rounded-lg border border-gray-700 bg-gray-800 p-0.5">
				<button
					type="button"
					onclick={() => { addSourceType = 'rtsp'; }}
					class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors {addSourceType === 'rtsp' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'}"
				>RTSP</button>
				<button
					type="button"
					onclick={() => { addSourceType = 'go2rtc'; loadGo2rtcStreams(); }}
					class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors {addSourceType === 'go2rtc' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'}"
				>go2rtc</button>
			</div>

			{#if addError}
				<p class="mb-3 rounded bg-red-950 px-3 py-2 text-sm text-red-400">{addError}</p>
			{/if}
			<form onsubmit={handleAdd} class="space-y-4">
				<div>
					<label for="add-name" class="mb-1 block text-sm font-medium text-gray-300">Name</label>
					<input
						id="add-name"
						type="text"
						bind:value={newName}
						required
						placeholder="e.g. Front Yard"
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

				{#if addSourceType === 'rtsp'}
					<div>
						<label for="add-url" class="mb-1 block text-sm font-medium text-gray-300">RTSP URL</label>
						<input
							id="add-url"
							type="text"
							bind:value={newUrl}
							required
							placeholder="rtsp://..."
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
				{:else}
					<div>
						<label for="add-go2rtc" class="mb-1 block text-sm font-medium text-gray-300">go2rtc Stream</label>
						{#if go2rtcLoading}
							<p class="text-sm text-gray-400">Loading streams...</p>
						{:else if go2rtcError}
							<p class="text-sm text-red-400">{go2rtcError}</p>
							{#if go2rtcError.includes('not configured') || go2rtcError.includes('400')}
								<a href="/settings" class="mt-1 text-sm text-blue-400 hover:text-blue-300">Configure go2rtc in Settings</a>
							{/if}
						{:else if go2rtcStreams.length === 0}
							<p class="text-sm text-gray-500">No streams found on go2rtc server.</p>
						{:else}
							<select
								id="add-go2rtc"
								bind:value={selectedGo2rtcName}
								required
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="" disabled>Select a stream</option>
								{#each go2rtcStreams as s}
									<option value={s.name}>{s.name}</option>
								{/each}
							</select>
						{/if}
					</div>
				{/if}

				<div class="flex justify-end gap-3">
					<button
						type="button"
						onclick={() => { showAddModal = false; }}
						class="rounded-lg px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={addLoading || (addSourceType === 'go2rtc' && !selectedGo2rtcName)}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{addLoading ? 'Adding...' : 'Add Stream'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={() => { deleteTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h2 class="mb-2 text-lg font-semibold text-gray-100">Delete Stream</h2>
			<p class="mb-4 text-sm text-gray-400">
				Are you sure you want to delete <strong class="text-gray-200">{deleteTarget.name}</strong>? This will also delete all associated profiles and captures.
			</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { deleteTarget = null; }}
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200"
				>
					Cancel
				</button>
				<button
					onclick={handleDelete}
					disabled={deleteLoading}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-50"
				>
					{deleteLoading ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}
