<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream, Timelapse, StorageStats } from '$lib/types';
	import StorageStatsComponent from '$lib/components/StorageStats.svelte';
	import StreamCard from '$lib/components/StreamCard.svelte';

	let health = $state<{ status: string; version: string } | null>(null);
	let storage = $state<StorageStats | null>(null);
	let streams = $state<Stream[]>([]);
	let timelapses = $state<Timelapse[]>([]);
	let profileCounts = $state<Record<number, number>>({});
	let error = $state<string | null>(null);

	$effect(() => {
		api.getHealth()
			.then((data) => { health = data; })
			.catch((err) => { error = err.message; });

		api.getStorage()
			.then((data) => { storage = data; })
			.catch(() => {});

		api.getStreams()
			.then(async (data) => {
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
			})
			.catch(() => {});

		api.getTimelapses({ limit: 5 })
			.then((data) => { timelapses = data; })
			.catch(() => {});
	});

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	function formatBytes(bytes: number | null): string {
		if (!bytes) return 'N/A';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold text-white">Dashboard</h1>
			{#if health}
				<p class="mt-1 text-sm text-gray-500">Lapsora v{health.version}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			{#if error}
				<span class="h-2.5 w-2.5 rounded-full bg-red-500"></span>
				<span class="text-sm text-red-400">Unreachable</span>
			{:else if health}
				<span class="h-2.5 w-2.5 rounded-full bg-green-500"></span>
				<span class="text-sm text-green-400">{health.status}</span>
			{:else}
				<span class="h-2.5 w-2.5 animate-pulse rounded-full bg-yellow-500"></span>
				<span class="text-sm text-gray-400">Checking...</span>
			{/if}
		</div>
	</div>

	{#if storage}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
			<StorageStatsComponent stats={storage} />
		</div>
	{/if}

	<div>
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-xl font-semibold text-gray-100">Streams</h2>
			<a href="/streams" class="text-sm text-blue-400 hover:text-blue-300">View all</a>
		</div>
		{#if streams.length === 0}
			<p class="text-sm text-gray-500">No streams configured.</p>
		{:else}
			<div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
				{#each streams as stream}
					<StreamCard {stream} profileCount={profileCounts[stream.id] ?? 0} />
				{/each}
			</div>
		{/if}
	</div>

	<div>
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-xl font-semibold text-gray-100">Recent Timelapses</h2>
			<a href="/timelapses" class="text-sm text-blue-400 hover:text-blue-300">View all</a>
		</div>
		{#if timelapses.length === 0}
			<p class="text-sm text-gray-500">No timelapses generated yet.</p>
		{:else}
			<div class="space-y-2">
				{#each timelapses as tl}
					<a
						href="/timelapses"
						class="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 p-4 transition-colors hover:border-gray-700"
					>
						<div class="flex items-center gap-3">
							<span class="rounded bg-purple-900 px-2 py-0.5 text-xs font-medium text-purple-300">{tl.format.toUpperCase()}</span>
							<span class="text-sm text-gray-200">{tl.period_type ?? 'custom'}</span>
							{#if tl.frame_count}
								<span class="text-xs text-gray-500">{tl.frame_count} frames</span>
							{/if}
						</div>
						<div class="flex items-center gap-4 text-sm text-gray-400">
							<span>{formatBytes(tl.file_size)}</span>
							<span>{formatDate(tl.created_at)}</span>
						</div>
					</a>
				{/each}
			</div>
		{/if}
	</div>
</div>
