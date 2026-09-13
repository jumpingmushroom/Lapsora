<script lang="ts">
	import { api } from '$lib/api';
	import type { RenderOptionsValue } from '$lib/types';
	import { renderEstimate, formatCount, formatRenderLength } from '$lib/estimates';

	interface Props {
		/** Bound render settings, in wire format. */
		value: RenderOptionsValue;
		/** Source dimensions of the capture plan, used to cap output resolution. */
		maxWidth?: number;
		maxHeight?: number;
		/** Unique per instance so two RenderOptions on one page don't share ids. */
		idPrefix: string;
		/** Rendered inside Basics, above the length controls (e.g. a time range). */
		basics?: import('svelte').Snippet;
		/** Frames this render will consume. null hides the length preview. */
		frameCount?: number | null;
		/** True when frameCount is derived rather than counted. */
		frameCountApproximate?: boolean;
	}

	let {
		value = $bindable(),
		maxWidth = Infinity,
		maxHeight = Infinity,
		idPrefix,
		basics,
		frameCount = null,
		frameCountApproximate = false
	}: Props = $props();

	let estimate = $derived(
		frameCount === null
			? null
			: renderEstimate(frameCount, value.fps_mode, value.fps, value.render_target_seconds)
	);

	const RESOLUTION_PRESETS: Record<string, [number, number]> = {
		'720p': [1280, 720],
		'1080p': [1920, 1080],
		'4k': [3840, 2160],
		'8k': [7680, 4320]
	};

	const POSITIONS = [
		{ value: 'top-left', label: 'Top left' },
		{ value: 'top-right', label: 'Top right' },
		{ value: 'bottom-left', label: 'Bottom left' },
		{ value: 'bottom-right', label: 'Bottom right' }
	];

	function detectResolutionPreset(w: number | null, h: number | null): string {
		if (!w || !h) return 'original';
		for (const [key, dims] of Object.entries(RESOLUTION_PRESETS)) {
			if (dims[0] === w && dims[1] === h) return key;
		}
		return 'custom';
	}

	let resolutionPreset = $state(detectResolutionPreset(value.output_width, value.output_height));

	function onResolutionChange() {
		const dims = RESOLUTION_PRESETS[resolutionPreset];
		if (dims) {
			value.output_width = dims[0];
			value.output_height = dims[1];
		} else {
			// 'original' and 'custom' both start from no explicit size; custom
			// then gets its own width/height inputs.
			value.output_width = null;
			value.output_height = null;
		}
	}

	// A plan change can leave a preset selected that the new source can't
	// produce. Fall back to the source resolution rather than upscaling.
	$effect(() => {
		const dims = RESOLUTION_PRESETS[resolutionPreset];
		if (dims && (dims[0] > maxWidth || dims[1] > maxHeight)) {
			resolutionPreset = 'original';
			value.output_width = null;
			value.output_height = null;
		}
	});

	let nvencAvailable = $state(false);
	let logoExists = $state(false);

	$effect(() => {
		api.getSystemInfo().then((info) => { nvencAvailable = info.nvenc_available; }).catch(() => {});
		api.getLogo().then((r) => { logoExists = r.exists; }).catch(() => {});
	});

	// GIF has no codec, no quality preset and no motion blur pass.
	let isGif = $derived(value.format === 'gif');
	let supportsCodec = $derived(value.format === 'mp4' || value.format === 'mkv');

	let overlayCount = $derived(
		[
			value.timestamp_overlay,
			value.weather_overlay,
			value.ha_overlay,
			value.heatmap_overlay,
			value.logo_overlay
		].filter(Boolean).length
	);

	// Sliders speak percent; the wire format is a fraction.
	let logoSizePct = $derived(Math.round(value.logo_size * 100));
	let logoOpacityPct = $derived(Math.round(value.logo_opacity * 100));

	const field =
		'w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
	const checkbox =
		'h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500';
	const label = 'mb-1 block text-sm font-medium text-gray-300';
	const summary =
		'flex cursor-pointer items-center gap-2 rounded-md py-2 text-sm font-semibold text-gray-200 marker:content-none hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500';
</script>

<div class="space-y-4">
	<!-- ── Basics ─────────────────────────────────────────────── -->
	<div class="space-y-4">
		{@render basics?.()}

		<div class="grid grid-cols-2 gap-3">
			<div>
				<label for="{idPrefix}-fps-mode" class={label}>Length</label>
				<select id="{idPrefix}-fps-mode" bind:value={value.fps_mode} class={field}>
					<option value="fixed">Fixed frame rate</option>
					<option value="target_duration">Target duration</option>
				</select>
			</div>
			{#if value.fps_mode === 'target_duration'}
				<div>
					<label for="{idPrefix}-target" class={label}>Target length (s)</label>
					<input
						id="{idPrefix}-target"
						type="number"
						bind:value={value.render_target_seconds}
						min="1"
						class={field}
					/>
				</div>
			{:else}
				<div>
					<label for="{idPrefix}-fps" class={label}>FPS</label>
					<input id="{idPrefix}-fps" type="number" bind:value={value.fps} min="1" max="120" class={field} />
				</div>
			{/if}
		</div>

		{#if estimate && frameCount !== null}
			<p class="rounded-md border border-gray-700 bg-gray-900/60 px-3 py-2 text-xs text-gray-300">
				{frameCountApproximate ? '~' : ''}<span class="font-semibold text-gray-100">{formatCount(frameCount)}</span>
				frames →
				<span class="font-semibold text-gray-100">{formatRenderLength(estimate.durationSeconds)}</span>
				at {estimate.fps} fps
				{#if frameCountApproximate}
					<span class="text-gray-500">(estimated from the capture interval)</span>
				{/if}
			</p>
		{:else if frameCount === 0}
			<p class="rounded-md border border-amber-800 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
				No frames in this range — there would be nothing to render.
			</p>
		{:else if value.fps_mode === 'target_duration'}
			<p class="text-xs text-gray-500">
				Frame rate is chosen when the render runs, so the result lands near
				{value.render_target_seconds}s however many frames the range holds.
			</p>
		{/if}

		<div>
			<label for="{idPrefix}-format" class={label}>Format</label>
			<select id="{idPrefix}-format" bind:value={value.format} class={field}>
				<option value="mp4">MP4</option>
				<option value="webm">WebM</option>
				<option value="gif">GIF</option>
				<option value="mkv">MKV</option>
			</select>
		</div>
	</div>

	<!-- ── Quality & output ───────────────────────────────────── -->
	<details class="rounded-md border border-gray-700 bg-gray-900/40 px-3">
		<summary class={summary}>
			<svg class="h-4 w-4 shrink-0 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			Quality &amp; output
		</summary>
		<div class="space-y-3 pb-3">
			{#if supportsCodec}
				<div>
					<label for="{idPrefix}-codec" class="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
						Codec
						{#if nvencAvailable}
							<span class="rounded bg-green-900/50 px-1.5 py-0.5 text-xs font-semibold text-green-300">GPU</span>
						{/if}
					</label>
					<select id="{idPrefix}-codec" bind:value={value.codec} class={field}>
						<option value="auto">Auto</option>
						<option value="h264">H.264</option>
						<option value="h265">H.265 (HEVC)</option>
					</select>
				</div>
			{/if}

			{#if !isGif}
				<div>
					<label for="{idPrefix}-resolution" class={label}>Output resolution</label>
					<select
						id="{idPrefix}-resolution"
						bind:value={resolutionPreset}
						onchange={onResolutionChange}
						class={field}
					>
						<option value="original">Original</option>
						{#each Object.entries(RESOLUTION_PRESETS) as [key, dims]}
							{#if dims[0] <= maxWidth && dims[1] <= maxHeight}
								<option value={key}>{key}</option>
							{/if}
						{/each}
						<option value="custom">Custom</option>
					</select>
				</div>

				{#if resolutionPreset === 'custom'}
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="{idPrefix}-out-w" class={label}>Width</label>
							<input
								id="{idPrefix}-out-w"
								type="number"
								bind:value={value.output_width}
								min="1"
								max={maxWidth === Infinity ? undefined : maxWidth}
								placeholder="Width"
								class={field}
							/>
						</div>
						<div>
							<label for="{idPrefix}-out-h" class={label}>Height</label>
							<input
								id="{idPrefix}-out-h"
								type="number"
								bind:value={value.output_height}
								min="1"
								max={maxHeight === Infinity ? undefined : maxHeight}
								placeholder="Height"
								class={field}
							/>
						</div>
					</div>
				{/if}

				<div>
					<label for="{idPrefix}-quality" class={label}>Quality</label>
					<select id="{idPrefix}-quality" bind:value={value.quality_preset} class={field}>
						<option value="low">Low</option>
						<option value="medium">Medium</option>
						<option value="high">High</option>
						<option value="lossless">Lossless</option>
					</select>
				</div>
			{/if}

			<div>
				<label for="{idPrefix}-deflicker" class={label}>Deflicker</label>
				<select id="{idPrefix}-deflicker" bind:value={value.deflicker} class={field}>
					<option value="off">Off</option>
					<option value="light">Light</option>
					<option value="medium">Medium</option>
					<option value="heavy">Heavy</option>
				</select>
			</div>

			{#if !isGif}
				<div>
					<label for="{idPrefix}-motion-blur" class={label}>Motion blur</label>
					<select id="{idPrefix}-motion-blur" bind:value={value.motion_blur} class={field}>
						<option value="off">Off</option>
						<option value="low">Low</option>
						<option value="medium">Medium</option>
						<option value="high">High</option>
					</select>
				</div>
			{/if}
		</div>
	</details>

	<!-- ── Overlays ───────────────────────────────────────────── -->
	<details class="rounded-md border border-gray-700 bg-gray-900/40 px-3">
		<summary class={summary}>
			<svg class="h-4 w-4 shrink-0 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
			Overlays
			{#if overlayCount > 0}
				<span class="rounded-full bg-blue-900/60 px-2 py-0.5 text-xs font-medium text-blue-300">{overlayCount} on</span>
			{/if}
		</summary>
		<div class="space-y-3 pb-3">
			<!-- Timestamp -->
			<div class="flex items-center gap-3">
				<input id="{idPrefix}-timestamp" type="checkbox" bind:checked={value.timestamp_overlay} class={checkbox} />
				<label for="{idPrefix}-timestamp" class="text-sm font-medium text-gray-300">Timestamp</label>
			</div>

			<!-- Weather -->
			<div class="flex items-center gap-3">
				<input id="{idPrefix}-weather" type="checkbox" bind:checked={value.weather_overlay} class={checkbox} />
				<label for="{idPrefix}-weather" class="text-sm font-medium text-gray-300">Weather</label>
			</div>
			{#if value.weather_overlay}
				<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="{idPrefix}-weather-pos" class={label}>Position</label>
							<select id="{idPrefix}-weather-pos" bind:value={value.weather_position} class={field}>
								{#each POSITIONS as pos}
									<option value={pos.value}>{pos.label}</option>
								{/each}
							</select>
						</div>
						<div>
							<label for="{idPrefix}-weather-style" class={label}>Style</label>
							<select id="{idPrefix}-weather-style" bind:value={value.weather_style} class={field}>
								<option value="glass">Glass (default)</option>
								<option value="badge">Badge</option>
								<option value="strip">Strip</option>
								<option value="minimal">Minimal</option>
							</select>
						</div>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="{idPrefix}-weather-size" class={label}>Font size</label>
							<input
								id="{idPrefix}-weather-size"
								type="number"
								bind:value={value.weather_font_size}
								min="8"
								max="96"
								class={field}
							/>
						</div>
						<div>
							<span class={label}>Unit</span>
							<div class="flex gap-4 pt-1.5">
								<label class="flex items-center gap-2 text-sm text-gray-300">
									<input type="radio" bind:group={value.weather_unit} value="C" class="text-blue-500" />
									&deg;C
								</label>
								<label class="flex items-center gap-2 text-sm text-gray-300">
									<input type="radio" bind:group={value.weather_unit} value="F" class="text-blue-500" />
									&deg;F
								</label>
							</div>
						</div>
					</div>
				</div>
			{/if}

			<!-- Home Assistant -->
			<div class="flex items-center gap-3">
				<input id="{idPrefix}-ha" type="checkbox" bind:checked={value.ha_overlay} class={checkbox} />
				<label for="{idPrefix}-ha" class="text-sm font-medium text-gray-300">Home Assistant sensors</label>
			</div>
			{#if value.ha_overlay}
				<div class="rounded-md border border-gray-700 bg-gray-900 p-3">
					<label for="{idPrefix}-ha-pos" class={label}>Position</label>
					<select id="{idPrefix}-ha-pos" bind:value={value.ha_overlay_position} class={field}>
						{#each POSITIONS as pos}
							<option value={pos.value}>{pos.label}</option>
						{/each}
					</select>
				</div>
			{/if}

			<!-- Heatmap -->
			<div class="flex items-center gap-3">
				<input id="{idPrefix}-heatmap" type="checkbox" bind:checked={value.heatmap_overlay} class={checkbox} />
				<label for="{idPrefix}-heatmap" class="text-sm font-medium text-gray-300">Activity heatmap</label>
			</div>
			{#if value.heatmap_overlay}
				<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="{idPrefix}-heatmap-mode" class={label}>Mode</label>
							<select id="{idPrefix}-heatmap-mode" bind:value={value.heatmap_mode} class={field}>
								<option value="cumulative">Cumulative</option>
								<option value="sliding">Sliding window</option>
							</select>
						</div>
						<div>
							<label for="{idPrefix}-heatmap-colormap" class={label}>Colormap</label>
							<select id="{idPrefix}-heatmap-colormap" bind:value={value.heatmap_colormap} class={field}>
								<option value="jet">Jet</option>
								<option value="inferno">Inferno</option>
								<option value="viridis">Viridis</option>
								<option value="turbo">Turbo</option>
							</select>
						</div>
					</div>
					<div>
						<label for="{idPrefix}-heatmap-threshold" class={label}>
							Threshold: {value.heatmap_threshold}
						</label>
						<input
							id="{idPrefix}-heatmap-threshold"
							type="range"
							bind:value={value.heatmap_threshold}
							min="1"
							max="100"
							class="w-full accent-blue-500"
						/>
					</div>
				</div>
			{/if}

			<!-- Logo -->
			<div class="flex items-center gap-3">
				<input id="{idPrefix}-logo" type="checkbox" bind:checked={value.logo_overlay} class={checkbox} />
				<label for="{idPrefix}-logo" class="text-sm font-medium text-gray-300">Logo / watermark</label>
			</div>
			{#if value.logo_overlay}
				<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
					{#if !logoExists}
						<p class="text-xs text-amber-400">No logo uploaded yet — add one in Settings → Branding.</p>
					{/if}
					<div>
						<label for="{idPrefix}-logo-pos" class={label}>Position</label>
						<select id="{idPrefix}-logo-pos" bind:value={value.logo_position} class={field}>
							{#each POSITIONS as pos}
								<option value={pos.value}>{pos.label}</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="{idPrefix}-logo-size" class={label}>Size: {logoSizePct}% of width</label>
						<input
							id="{idPrefix}-logo-size"
							type="range"
							min="2"
							max="50"
							value={logoSizePct}
							oninput={(e) => { value.logo_size = Number(e.currentTarget.value) / 100; }}
							class="w-full accent-blue-500"
						/>
					</div>
					<div>
						<label for="{idPrefix}-logo-opacity" class={label}>Opacity: {logoOpacityPct}%</label>
						<input
							id="{idPrefix}-logo-opacity"
							type="range"
							min="10"
							max="100"
							value={logoOpacityPct}
							oninput={(e) => { value.logo_opacity = Number(e.currentTarget.value) / 100; }}
							class="w-full accent-blue-500"
						/>
					</div>
				</div>
			{/if}
		</div>
	</details>
</div>

<style>
	/* Rotate the chevron when the section is open. */
	details[open] > summary > svg {
		transform: rotate(90deg);
	}
	summary > svg {
		transition: transform 150ms ease;
	}
	@media (prefers-reduced-motion: reduce) {
		summary > svg {
			transition: none;
		}
	}
	/* Safari still paints a disclosure triangle without this. */
	summary::-webkit-details-marker {
		display: none;
	}
</style>
