<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream } from '$lib/types';

	let streams = $state<Stream[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		api.getStreams()
			.then((data) => {
				streams = data;
				loading = false;
			})
			.catch((err) => {
				error = err.message;
				loading = false;
			});
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold text-white">Streams</h1>
		<button
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
				<a
					href="/streams/{stream.id}"
					class="rounded-xl border border-gray-800 bg-gray-900 p-5 transition-colors hover:border-gray-700"
				>
					<div class="flex items-center justify-between">
						<h3 class="font-medium text-white">{stream.name}</h3>
						<span
							class="h-2.5 w-2.5 rounded-full {stream.enabled ? 'bg-green-500' : 'bg-gray-600'}"
						></span>
					</div>
					<p class="mt-2 truncate text-sm text-gray-500">{stream.url}</p>
				</a>
			{/each}
		</div>
	{/if}
</div>
