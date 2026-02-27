<script lang="ts">
	import type { StorageStats } from '$lib/types';

	interface Props {
		stats: StorageStats;
	}

	let { stats }: Props = $props();

	function formatBytes(bytes: number): string {
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
	}

	let capturesPct = $derived(stats.disk_total_bytes > 0 ? (stats.captures_size_bytes / stats.disk_total_bytes) * 100 : 0);
	let timelapsesPct = $derived(stats.disk_total_bytes > 0 ? (stats.timelapses_size_bytes / stats.disk_total_bytes) * 100 : 0);
	let capturesDisplay = $derived(capturesPct > 0 ? Math.max(capturesPct, 1) : 0);
	let timelapsesDisplay = $derived(timelapsesPct > 0 ? Math.max(timelapsesPct, 1) : 0);
	let freeDisplay = $derived(100 - capturesDisplay - timelapsesDisplay);
</script>

<div class="rounded-lg bg-gray-800 p-4">
	<h3 class="mb-3 text-lg font-semibold text-gray-100">Storage</h3>

	<div class="mb-4 flex h-4 w-full overflow-hidden rounded-full bg-gray-900">
		{#if capturesPct > 0}
			<div class="bg-blue-500" style="width: {capturesDisplay}%" title="Captures: {formatBytes(stats.captures_size_bytes)}"></div>
		{/if}
		{#if timelapsesPct > 0}
			<div class="bg-purple-500" style="width: {timelapsesDisplay}%" title="Timelapses: {formatBytes(stats.timelapses_size_bytes)}"></div>
		{/if}
		{#if freeDisplay > 0}
			<div class="bg-gray-700" style="width: {freeDisplay}%" title="Free: {formatBytes(stats.disk_free_bytes)}"></div>
		{/if}
	</div>

	<div class="mb-2 flex gap-4 text-xs text-gray-400">
		<span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-full bg-blue-500"></span> Captures</span>
		<span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-full bg-purple-500"></span> Timelapses</span>
		<span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-full bg-gray-700"></span> Free</span>
	</div>

	<div class="grid grid-cols-2 gap-3 text-sm">
		<div>
			<span class="text-gray-500">Captures:</span>
			<span class="ml-1 text-gray-300">{stats.captures_count} ({formatBytes(stats.captures_size_bytes)})</span>
		</div>
		<div>
			<span class="text-gray-500">Timelapses:</span>
			<span class="ml-1 text-gray-300">{stats.timelapses_count} ({formatBytes(stats.timelapses_size_bytes)})</span>
		</div>
		<div>
			<span class="text-gray-500">Total used:</span>
			<span class="ml-1 text-gray-300">{formatBytes(stats.total_size_bytes)}</span>
		</div>
		<div>
			<span class="text-gray-500">Disk free:</span>
			<span class="ml-1 text-gray-300">{formatBytes(stats.disk_free_bytes)}</span>
		</div>
	</div>
</div>
