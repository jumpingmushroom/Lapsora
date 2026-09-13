<script lang="ts">
	import { api } from '$lib/api';
	import { formatInterval } from '$lib/utils';
	import {
		PLAN_INTERVALS,
		PLAN_RESOLUTIONS,
		effectiveInterval,
		effectiveDimensions
	} from '$lib/capturePlan';
	import type { CapturePlanDraft } from '$lib/capturePlan';
	import type { ProfileTemplate } from '$lib/types';
	import CaptureEstimate from './CaptureEstimate.svelte';

	interface Props {
		value: CapturePlanDraft;
		/** Named in the intro line, so it reads about this camera specifically. */
		cameraName?: string;
		/** Estimate basis for a camera that has no frames yet (the source test). */
		sampleBytes?: number | null;
		sampleWidth?: number | null;
		sampleHeight?: number | null;
		/** Estimate basis for a camera that already captures. */
		profileId?: number | null;
		/** Unique per instance so two of these on one page don't share ids. */
		idPrefix?: string;
	}

	let {
		value = $bindable(),
		cameraName = '',
		sampleBytes = null,
		sampleWidth = null,
		sampleHeight = null,
		profileId = null,
		idPrefix = 'plan'
	}: Props = $props();

	let presets = $state<ProfileTemplate[]>([]);
	let presetCategory = $state<string | null>(null);

	// Self-loading keeps the step usable anywhere without the caller having to
	// know it needs presets.
	$effect(() => {
		api.getProfileTemplates()
			.then((p) => { presets = p; })
			.catch(() => { presets = []; });
	});

	let categories = $derived([...new Set(presets.map((p) => p.category))].sort());
	let visiblePresets = $derived(
		presetCategory ? presets.filter((p) => p.category === presetCategory) : presets
	);

	let interval = $derived(effectiveInterval(value, presets));
	let dims = $derived(effectiveDimensions(value, presets));

	// The select needs an index; the draft stores real dimensions.
	let resolutionIndex = $derived.by(() => {
		if (!value.resolution_width || !value.resolution_height) return 0;
		const i = PLAN_RESOLUTIONS.findIndex(
			(r) => r.dims && r.dims[0] === value.resolution_width && r.dims[1] === value.resolution_height
		);
		return i === -1 ? 0 : i;
	});

	function onResolutionChange(e: Event) {
		const chosen = PLAN_RESOLUTIONS[Number((e.currentTarget as HTMLSelectElement).value)];
		value.resolution_width = chosen?.dims ? chosen.dims[0] : null;
		value.resolution_height = chosen?.dims ? chosen.dims[1] : null;
	}

	function selectPreset(preset: ProfileTemplate) {
		value.presetId = preset.id;
		value.custom = false;
		// Default the name to the preset's, but only while the user hasn't
		// typed one — retyping it on every card click would be maddening.
		if (!value.name.trim()) value.name = preset.name;
	}

	const fieldClass =
		'w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
	const labelClass = 'mb-1 block text-sm font-medium text-gray-300';
</script>

<p class="text-sm text-gray-400">
	A capture plan decides how often {cameraName || 'this camera'} takes a frame. Nothing is
	captured without one.
</p>

{#if categories.length > 1}
	<div class="flex flex-wrap gap-1.5">
		<button
			type="button"
			onclick={() => { presetCategory = null; }}
			class="rounded-full px-3 py-1 text-xs font-medium transition-colors {presetCategory === null ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}"
		>All</button>
		{#each categories as cat}
			<button
				type="button"
				onclick={() => { presetCategory = cat; }}
				class="rounded-full px-3 py-1 text-xs font-medium transition-colors {presetCategory === cat ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}"
			>{cat}</button>
		{/each}
	</div>
{/if}

<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
	{#each visiblePresets as preset}
		<button
			type="button"
			onclick={() => selectPreset(preset)}
			class="flex flex-col items-start rounded-lg border p-3 text-left transition-colors {
				!value.custom && value.presetId === preset.id
					? 'border-blue-500 bg-blue-950/40'
					: 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
			}"
		>
			<span class="text-sm font-medium text-gray-100">{preset.name}</span>
			{#if preset.description}
				<span class="mt-0.5 text-xs text-gray-500">{preset.description}</span>
			{/if}
			<span class="mt-1.5 flex flex-wrap gap-1">
				<span class="rounded bg-gray-900 px-1.5 py-0.5 text-xs text-gray-400">{formatInterval(preset.interval_seconds)}</span>
				{#if preset.resolution_width && preset.resolution_height}
					<span class="rounded bg-gray-900 px-1.5 py-0.5 text-xs text-gray-400">{preset.resolution_width}x{preset.resolution_height}</span>
				{/if}
				{#if preset.hdr_enabled}
					<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
				{/if}
			</span>
		</button>
	{/each}

	<button
		type="button"
		onclick={() => { value.custom = true; value.presetId = null; }}
		class="flex flex-col items-start rounded-lg border border-dashed p-3 text-left transition-colors {
			value.custom ? 'border-blue-500 bg-blue-950/40' : 'border-gray-700 hover:border-gray-600'
		}"
	>
		<span class="text-sm font-medium text-gray-100">Custom</span>
		<span class="mt-0.5 text-xs text-gray-500">Set the interval yourself</span>
	</button>
</div>

<div class="space-y-3 rounded-lg border border-gray-800 bg-gray-800/40 p-3">
	<div>
		<label for="{idPrefix}-name" class={labelClass}>Plan name</label>
		<input
			id="{idPrefix}-name"
			type="text"
			bind:value={value.name}
			placeholder="e.g. Front Yard"
			class={fieldClass}
		/>
	</div>

	{#if value.custom}
		<div>
			<span class={labelClass}>Capture a frame every</span>
			<div class="flex flex-wrap gap-1.5">
				{#each PLAN_INTERVALS as seconds}
					<button
						type="button"
						onclick={() => { value.interval_seconds = seconds; }}
						class="rounded-full px-3 py-1 text-xs font-medium transition-colors {value.interval_seconds === seconds ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'}"
					>{formatInterval(seconds)}</button>
				{/each}
			</div>
		</div>
		<div class="grid grid-cols-2 gap-3">
			<div>
				<label for="{idPrefix}-res" class={labelClass}>Resolution</label>
				<select id="{idPrefix}-res" value={resolutionIndex} onchange={onResolutionChange} class={fieldClass}>
					{#each PLAN_RESOLUTIONS as res, i}
						<option value={i}>{res.label}</option>
					{/each}
				</select>
			</div>
			<div>
				<label for="{idPrefix}-quality" class={labelClass}>Quality: {value.quality}</label>
				<input
					id="{idPrefix}-quality"
					type="range"
					min="1"
					max="100"
					bind:value={value.quality}
					class="mt-2 w-full accent-blue-500"
				/>
			</div>
		</div>
		<p class="text-xs text-gray-500">
			HDR, IR-only capture, active hours and sensor overlays can be set on the camera once the
			plan exists.
		</p>
	{/if}

	{#if interval > 0}
		<CaptureEstimate
			intervalSeconds={interval}
			resolutionWidth={dims?.w ?? null}
			resolutionHeight={dims?.h ?? null}
			{sampleBytes}
			{sampleWidth}
			{sampleHeight}
			{profileId}
		/>
	{/if}
</div>
