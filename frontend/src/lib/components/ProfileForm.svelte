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
	let weather_enabled = $state(profile?.weather_enabled ?? false);
	let capture_mode = $state(profile?.capture_mode ?? 'always');
	let active_start_time = $state(profile?.active_start_time ?? '06:00');
	let active_end_time = $state(profile?.active_end_time ?? '20:00');
	let sun_offset_minutes = $state(profile?.sun_offset_minutes ?? 0);

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		const data: ProfileCreate | ProfileUpdate = {
			name,
			interval_seconds,
			resolution_width: resolution_width || null,
			resolution_height: resolution_height || null,
			quality,
			hdr_enabled,
			weather_enabled,
			capture_mode,
			active_start_time: capture_mode === 'manual' ? active_start_time : null,
			active_end_time: capture_mode === 'manual' ? active_end_time : null,
			sun_offset_minutes: capture_mode === 'sun' ? sun_offset_minutes : 0
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

	<div class="flex items-center gap-3">
		<input
			id="weather"
			type="checkbox"
			bind:checked={weather_enabled}
			class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
		/>
		<label for="weather" class="text-sm font-medium text-gray-300">Collect weather data</label>
	</div>

	<!-- Capture Mode -->
	<div>
		<label class="mb-2 block text-sm font-medium text-gray-300">Active hours</label>
		<div class="flex gap-4">
			<label class="flex items-center gap-2 text-sm text-gray-300">
				<input type="radio" bind:group={capture_mode} value="always" class="text-blue-500" />
				Always
			</label>
			<label class="flex items-center gap-2 text-sm text-gray-300">
				<input type="radio" bind:group={capture_mode} value="manual" class="text-blue-500" />
				Manual hours
			</label>
			<label class="flex items-center gap-2 text-sm text-gray-300">
				<input type="radio" bind:group={capture_mode} value="sun" class="text-blue-500" />
				Sunrise/Sunset
			</label>
		</div>
	</div>

	{#if capture_mode === 'manual'}
		<div class="grid grid-cols-2 gap-4">
			<div>
				<label for="active-start" class="mb-1 block text-sm font-medium text-gray-300">Start time</label>
				<input
					id="active-start"
					type="time"
					bind:value={active_start_time}
					class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
			</div>
			<div>
				<label for="active-end" class="mb-1 block text-sm font-medium text-gray-300">End time</label>
				<input
					id="active-end"
					type="time"
					bind:value={active_end_time}
					class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
			</div>
		</div>
		<p class="text-xs text-gray-500">If start is after end, the window spans overnight (e.g. 22:00–04:00).</p>
	{/if}

	{#if capture_mode === 'sun'}
		<div>
			<label for="sun-offset" class="mb-1 block text-sm font-medium text-gray-300">Offset (minutes)</label>
			<input
				id="sun-offset"
				type="number"
				bind:value={sun_offset_minutes}
				class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			/>
			<p class="mt-1 text-xs text-gray-500">Positive values extend the window (capture before sunrise / after sunset). Negative values shrink it. Requires location in Settings.</p>
		</div>
	{/if}

	<button
		type="submit"
		class="w-full rounded-md bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700"
	>
		{profile ? 'Update Profile' : 'Create Profile'}
	</button>
</form>
