<script lang="ts">
	import { api } from '$lib/api';
	import type { ProfileTemplate, ProfileTemplateCreate } from '$lib/types';

	let templates = $state<ProfileTemplate[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let activeCategory = $state<string | null>(null);

	// Create form
	let showCreateForm = $state(false);
	let newName = $state('');
	let newCategory = $state('');
	let newDescription = $state('');
	let newInterval = $state(60);
	let newWidth = $state<number | null>(1920);
	let newHeight = $state<number | null>(1080);
	let newQuality = $state(85);
	let newHdr = $state(false);
	let creating = $state(false);

	let categories = $derived([...new Set(templates.map((t) => t.category))].sort());
	let filtered = $derived(
		activeCategory ? templates.filter((t) => t.category === activeCategory) : templates
	);
	let grouped = $derived(() => {
		const map = new Map<string, ProfileTemplate[]>();
		for (const t of filtered) {
			const list = map.get(t.category) || [];
			list.push(t);
			map.set(t.category, list);
		}
		return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
	});

	async function load() {
		loading = true;
		error = null;
		try {
			templates = await api.getProfileTemplates();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load templates';
		} finally {
			loading = false;
		}
	}

	$effect(() => { load(); });

	function formatInterval(seconds: number): string {
		if (seconds >= 3600) return `${(seconds / 3600).toFixed(seconds % 3600 === 0 ? 0 : 1)}h`;
		if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
		return `${seconds}s`;
	}

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		creating = true;
		try {
			const data: ProfileTemplateCreate = {
				name: newName,
				category: newCategory,
				description: newDescription,
				interval_seconds: newInterval,
				resolution_width: newWidth || null,
				resolution_height: newHeight || null,
				quality: newQuality,
				hdr_enabled: newHdr
			};
			await api.createProfileTemplate(data);
			showCreateForm = false;
			newName = '';
			newCategory = '';
			newDescription = '';
			newInterval = 60;
			newWidth = 1920;
			newHeight = 1080;
			newQuality = 85;
			newHdr = false;
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to create template');
		} finally {
			creating = false;
		}
	}

	async function deleteTemplate(t: ProfileTemplate) {
		if (!confirm(`Delete template "${t.name}"?`)) return;
		try {
			await api.deleteProfileTemplate(t.id);
			await load();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete');
		}
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold text-white">Profile Templates</h1>
		<button
			onclick={() => { showCreateForm = !showCreateForm; }}
			class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			{showCreateForm ? 'Cancel' : 'Create Template'}
		</button>
	</div>

	{#if showCreateForm}
		<div class="rounded-xl border border-gray-700 bg-gray-800 p-5">
			<h2 class="mb-4 text-lg font-semibold text-gray-100">New Template</h2>
			<form onsubmit={handleCreate} class="space-y-4">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<div>
						<label for="tpl-name" class="mb-1 block text-sm font-medium text-gray-300">Name</label>
						<input id="tpl-name" type="text" bind:value={newName} required class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none" />
					</div>
					<div>
						<label for="tpl-cat" class="mb-1 block text-sm font-medium text-gray-300">Category</label>
						<input id="tpl-cat" type="text" bind:value={newCategory} required placeholder="e.g. Nature, Traffic" class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
					</div>
				</div>
				<div>
					<label for="tpl-desc" class="mb-1 block text-sm font-medium text-gray-300">Description</label>
					<input id="tpl-desc" type="text" bind:value={newDescription} class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
				</div>
				<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
					<div>
						<label for="tpl-int" class="mb-1 block text-sm font-medium text-gray-300">Interval (s)</label>
						<input id="tpl-int" type="number" bind:value={newInterval} min="1" class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none" />
					</div>
					<div>
						<label for="tpl-w" class="mb-1 block text-sm font-medium text-gray-300">Width</label>
						<input id="tpl-w" type="number" bind:value={newWidth} placeholder="Auto" class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
					</div>
					<div>
						<label for="tpl-h" class="mb-1 block text-sm font-medium text-gray-300">Height</label>
						<input id="tpl-h" type="number" bind:value={newHeight} placeholder="Auto" class="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
					</div>
					<div>
						<label for="tpl-q" class="mb-1 block text-sm font-medium text-gray-300">Quality: {newQuality}</label>
						<input id="tpl-q" type="range" bind:value={newQuality} min="1" max="100" class="mt-2 w-full accent-blue-500" />
					</div>
				</div>
				<label class="flex items-center gap-2">
					<input type="checkbox" bind:checked={newHdr} class="rounded border-gray-600 bg-gray-900 text-blue-500" />
					<span class="text-sm text-gray-300">HDR enabled</span>
				</label>
				<button type="submit" disabled={creating} class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50">
					{creating ? 'Creating...' : 'Create Template'}
				</button>
			</form>
		</div>
	{/if}

	{#if loading}
		<p class="text-gray-400">Loading templates...</p>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
			<p class="text-sm text-red-400">{error}</p>
		</div>
	{:else}
		<!-- Category filter tabs -->
		<div class="flex flex-wrap gap-2">
			<button
				onclick={() => { activeCategory = null; }}
				class="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors {activeCategory === null ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}"
			>
				All
			</button>
			{#each categories as cat}
				<button
					onclick={() => { activeCategory = cat; }}
					class="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors {activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}"
				>
					{cat}
				</button>
			{/each}
		</div>

		<!-- Grouped template cards -->
		{#each grouped() as [category, items]}
			<div>
				<h2 class="mb-3 text-lg font-semibold text-gray-300">{category}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
					{#each items as t}
						<div class="rounded-xl border border-gray-800 bg-gray-900 p-4">
							<div class="mb-2 flex items-start justify-between">
								<div>
									<h3 class="text-sm font-semibold text-gray-100">{t.name}</h3>
									{#if t.description}
										<p class="mt-0.5 text-xs text-gray-500">{t.description}</p>
									{/if}
								</div>
								{#if t.is_system}
									<span class="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">System</span>
								{:else}
									<button
										onclick={() => deleteTemplate(t)}
										class="rounded px-2 py-0.5 text-xs text-red-400 transition-colors hover:bg-red-950 hover:text-red-300"
									>
										Delete
									</button>
								{/if}
							</div>
							<div class="flex flex-wrap gap-1.5">
								<span class="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400">{formatInterval(t.interval_seconds)}</span>
								{#if t.resolution_width && t.resolution_height}
									<span class="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400">{t.resolution_width}x{t.resolution_height}</span>
								{/if}
								<span class="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400">Q{t.quality}</span>
								{#if t.hdr_enabled}
									<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/each}

		{#if templates.length === 0}
			<p class="text-gray-500">No templates yet.</p>
		{/if}
	{/if}
</div>
