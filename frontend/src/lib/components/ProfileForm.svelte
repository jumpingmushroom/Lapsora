<script lang="ts">
	import type { Profile, ProfileCreate, ProfileUpdate } from '$lib/types';

	interface Props {
		profile?: Profile | null;
		mode?: 'profile' | 'template';
		onsubmit: (data: ProfileCreate | ProfileUpdate) => void;
	}

	let { profile = null, mode = 'profile', onsubmit }: Props = $props();

	let name = $state(profile?.name ?? '');
	let interval_seconds = $state(profile?.interval_seconds ?? 300);
	let resolution_width = $state<number | null>(profile?.resolution_width ?? null);
	let resolution_height = $state<number | null>(profile?.resolution_height ?? null);
	let quality = $state(profile?.quality ?? 85);
	let hdr_enabled = $state(profile?.hdr_enabled ?? false);

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		const data: ProfileCreate | ProfileUpdate = {
			name,
			interval_seconds,
			resolution_width: resolution_width || null,
			resolution_height: resolution_height || null,
			quality,
			hdr_enabled
		};
		onsubmit(data);
	}
</script>

<form onsubmit={handleSubmit} class="space-y-5">
	<div>
		<label for="name" class="mb-1 block text-sm font-medium text-gray-300">Name</label>
		<input
			id="name"
			type="text"
			bind:value={name}
			required
			class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		/>
	</div>

	<div>
		<label for="interval" class="mb-1 block text-sm font-medium text-gray-300">Capture interval (seconds)</label>
		<input
			id="interval"
			type="number"
			bind:value={interval_seconds}
			min="1"
			class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		/>
	</div>

	<div class="grid grid-cols-2 gap-4">
		<div>
			<label for="res-w" class="mb-1 block text-sm font-medium text-gray-300">Width</label>
			<input
				id="res-w"
				type="number"
				bind:value={resolution_width}
				placeholder="Auto"
				class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			/>
		</div>
		<div>
			<label for="res-h" class="mb-1 block text-sm font-medium text-gray-300">Height</label>
			<input
				id="res-h"
				type="number"
				bind:value={resolution_height}
				placeholder="Auto"
				class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			/>
		</div>
	</div>

	<div>
		<label for="quality" class="mb-1 block text-sm font-medium text-gray-300">Quality: {quality}</label>
		<input
			id="quality"
			type="range"
			bind:value={quality}
			min="1"
			max="100"
			class="w-full accent-blue-500"
		/>
	</div>

	<div class="flex items-center gap-3">
		<input
			id="hdr"
			type="checkbox"
			bind:checked={hdr_enabled}
			class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
		/>
		<label for="hdr" class="text-sm font-medium text-gray-300">HDR enabled</label>
	</div>

	<button
		type="submit"
		class="w-full rounded-md bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700"
	>
		{profile ? 'Update Profile' : 'Create Profile'}
	</button>
</form>
