<script lang="ts">
	import { api } from '$lib/api';

	let health = $state<{ status: string; version: string } | null>(null);
	let error = $state<string | null>(null);

	$effect(() => {
		api.getHealth()
			.then((data) => {
				health = data;
			})
			.catch((err) => {
				error = err.message;
			});
	});
</script>

<div class="space-y-6">
	<h1 class="text-3xl font-bold text-white">Dashboard</h1>

	<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
		<h2 class="mb-3 text-sm font-medium text-gray-400">System Health</h2>
		{#if error}
			<div class="flex items-center gap-2">
				<span class="h-2.5 w-2.5 rounded-full bg-red-500"></span>
				<span class="text-sm text-red-400">Unreachable: {error}</span>
			</div>
		{:else if health}
			<div class="flex items-center gap-2">
				<span class="h-2.5 w-2.5 rounded-full bg-green-500"></span>
				<span class="text-sm text-green-400">{health.status}</span>
				<span class="text-xs text-gray-500">v{health.version}</span>
			</div>
		{:else}
			<div class="flex items-center gap-2">
				<span class="h-2.5 w-2.5 animate-pulse rounded-full bg-yellow-500"></span>
				<span class="text-sm text-gray-400">Checking...</span>
			</div>
		{/if}
	</div>
</div>
