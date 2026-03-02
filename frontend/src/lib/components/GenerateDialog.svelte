<script lang="ts">
	import { api } from '$lib/api';

	interface Props {
		profileOptions: { id: number; label: string; resolution_width: number | null; resolution_height: number | null }[];
		open: boolean;
		onclose: () => void;
	}

	let { profileOptions, open, onclose }: Props = $props();
	let selectedProfileId = $state(profileOptions[0]?.id ?? 0);

	type Preset = 'last24h' | 'today' | 'yesterday' | 'last7d' | 'last30d' | 'thisWeek' | 'lastWeek' | 'custom';

	const PRESETS: { key: Preset; label: string }[] = [
		{ key: 'last24h', label: 'Last 24h' },
		{ key: 'today', label: 'Today' },
		{ key: 'yesterday', label: 'Yesterday' },
		{ key: 'last7d', label: 'Last 7d' },
		{ key: 'last30d', label: 'Last 30d' },
		{ key: 'thisWeek', label: 'This week' },
		{ key: 'lastWeek', label: 'Last week' },
		{ key: 'custom', label: 'Custom' },
	];

	let selectedPreset = $state<Preset>('last24h');
	let customStartDate = $state('');
	let customStartTime = $state('00:00');
	let customEndDate = $state('');
	let customEndTime = $state('23:59');

	function computePresetRange(preset: Preset): { start: string; end: string } | null {
		const now = new Date();
		let start: Date;
		let end: Date = now;

		switch (preset) {
			case 'last24h':
				start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
				break;
			case 'today':
				start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
				break;
			case 'yesterday': {
				const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
				start = y;
				end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
				break;
			}
			case 'last7d':
				start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
				break;
			case 'last30d':
				start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
				break;
			case 'thisWeek': {
				const day = now.getDay();
				const diff = day === 0 ? 6 : day - 1;
				start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
				break;
			}
			case 'lastWeek': {
				const day = now.getDay();
				const diff = day === 0 ? 6 : day - 1;
				const thisMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
				start = new Date(thisMonday.getTime() - 7 * 24 * 60 * 60 * 1000);
				end = new Date(thisMonday.getTime() - 1000);
				break;
			}
			case 'custom':
				return null;
		}

		return {
			start: start.toISOString().slice(0, 19),
			end: end.toISOString().slice(0, 19),
		};
	}

	let period_start = $derived.by(() => {
		if (selectedPreset === 'custom') {
			if (!customStartDate) return '';
			return `${customStartDate}T${customStartTime || '00:00'}:00`;
		}
		return computePresetRange(selectedPreset)?.start ?? '';
	});

	let period_end = $derived.by(() => {
		if (selectedPreset === 'custom') {
			if (!customEndDate) return '';
			return `${customEndDate}T${customEndTime || '23:59'}:00`;
		}
		return computePresetRange(selectedPreset)?.end ?? '';
	});
	let fps = $state(24);
	let format = $state('mp4');
	let deflicker = $state('medium');
	let motion_blur = $state('off');
	let timestamp_overlay = $state(false);
	let weather_overlay = $state(false);
	let weather_position = $state('bottom-right');
	let weather_font_size = $state(24);
	let weather_unit = $state('C');
	let heatmap_overlay = $state(false);
	let heatmap_mode = $state('cumulative');
	let heatmap_opacity = $state(0.4);
	let heatmap_colormap = $state('jet');
	let heatmap_threshold = $state(10);
	let codec = $state('auto');
	let resolution_preset = $state('original');
	let output_width = $state<number | null>(null);
	let output_height = $state<number | null>(null);
	let quality_preset = $state('medium');
	let loading = $state(false);
	let error = $state('');
	let nvencAvailable = $state(false);

	$effect(() => {
		api.getSystemInfo().then((info) => {
			nvencAvailable = info.nvenc_available;
		}).catch(() => {});
	});

	let selectedProfile = $derived(profileOptions.find(p => p.id === selectedProfileId));
	let maxWidth = $derived(selectedProfile?.resolution_width ?? Infinity);
	let maxHeight = $derived(selectedProfile?.resolution_height ?? Infinity);

	// Reset resolution when profile changes and current preset exceeds source
	$effect(() => {
		selectedProfileId;
		const dims = RESOLUTION_PRESETS[resolution_preset];
		if (dims && (dims[0] > maxWidth || dims[1] > maxHeight)) {
			resolution_preset = 'original';
			output_width = null;
			output_height = null;
		}
	});

	const RESOLUTION_PRESETS: Record<string, [number, number] | null> = {
		original: null,
		'720p': [1280, 720],
		'1080p': [1920, 1080],
		'4k': [3840, 2160],
		'8k': [7680, 4320]
	};

	function onResolutionChange() {
		if (resolution_preset === 'custom') {
			output_width = null;
			output_height = null;
		} else {
			const dims = RESOLUTION_PRESETS[resolution_preset];
			if (dims) {
				output_width = dims[0];
				output_height = dims[1];
			} else {
				output_width = null;
				output_height = null;
			}
		}
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		loading = true;
		error = '';
		try {
			await api.generateTimelapse(selectedProfileId, {
				period_start: period_start || undefined,
				period_end: period_end || undefined,
				fps,
				format,
				deflicker,
			motion_blur: format !== 'gif' ? motion_blur : undefined,
				timestamp_overlay,
			weather_overlay,
			weather_position: weather_overlay ? weather_position : undefined,
			weather_font_size: weather_overlay ? weather_font_size : undefined,
			weather_unit: weather_overlay ? weather_unit : undefined,
			heatmap_overlay,
			heatmap_mode: heatmap_overlay ? heatmap_mode : undefined,
			heatmap_opacity: heatmap_overlay ? heatmap_opacity : undefined,
			heatmap_colormap: heatmap_overlay ? heatmap_colormap : undefined,
		heatmap_threshold: heatmap_overlay ? heatmap_threshold : undefined,
			codec: (format === 'mp4' || format === 'mkv') ? codec : undefined,
			output_width: output_width || undefined,
			output_height: output_height || undefined,
			quality_preset: format !== 'gif' ? quality_preset : undefined
			});
			onclose();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Generation failed';
		} finally {
			loading = false;
		}
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) onclose();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
		onclick={handleBackdrop}
		onkeydown={() => {}}
	>
		<div class="w-full max-w-md rounded-lg bg-gray-800 p-6">
			<h2 class="mb-4 text-xl font-semibold text-gray-100">Generate Timelapse</h2>

			{#if error}
				<p class="mb-3 rounded-md bg-red-900/50 px-3 py-2 text-sm text-red-300">{error}</p>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<label for="gen-profile" class="mb-1 block text-sm font-medium text-gray-300">Profile</label>
					<select
						id="gen-profile"
						bind:value={selectedProfileId}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						{#each profileOptions as opt}
							<option value={opt.id}>{opt.label}</option>
						{/each}
					</select>
				</div>

				<div>
					<label class="mb-1.5 block text-sm font-medium text-gray-300">Time Range</label>
					<div class="flex flex-wrap gap-1.5">
						{#each PRESETS as preset}
							<button
								type="button"
								onclick={() => { selectedPreset = preset.key; }}
								class="rounded-full px-3 py-1 text-xs font-medium transition-colors {
									selectedPreset === preset.key
										? 'bg-blue-600 text-white'
										: 'bg-gray-700 text-gray-300 hover:bg-gray-600'
								}"
							>
								{preset.label}
							</button>
						{/each}
					</div>
				</div>

				{#if selectedPreset === 'custom'}
					<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
						<div>
							<label for="gen-start-date" class="mb-1 block text-sm font-medium text-gray-300">Start</label>
							<div class="flex gap-2">
								<input
									id="gen-start-date"
									type="date"
									bind:value={customStartDate}
									class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
								<input
									id="gen-start-time"
									type="time"
									bind:value={customStartTime}
									class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
							</div>
						</div>
						<div>
							<label for="gen-end-date" class="mb-1 block text-sm font-medium text-gray-300">End</label>
							<div class="flex gap-2">
								<input
									id="gen-end-date"
									type="date"
									bind:value={customEndDate}
									class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
								<input
									id="gen-end-time"
									type="time"
									bind:value={customEndTime}
									class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
							</div>
						</div>
					</div>
				{/if}

				<div>
					<label for="gen-fps" class="mb-1 block text-sm font-medium text-gray-300">FPS</label>
					<input
						id="gen-fps"
						type="number"
						bind:value={fps}
						min="1"
						max="60"
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

				<div>
					<label for="gen-format" class="mb-1 block text-sm font-medium text-gray-300">Format</label>
					<select
						id="gen-format"
						bind:value={format}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						<option value="mp4">MP4</option>
						<option value="webm">WebM</option>
						<option value="gif">GIF</option>
						<option value="mkv">MKV</option>
					</select>
				</div>

				{#if format === 'mp4' || format === 'mkv'}
					<div>
						<label for="gen-codec" class="mb-1 flex items-center gap-2 text-sm font-medium text-gray-300">
						Codec
						{#if nvencAvailable}
							<span class="rounded bg-green-900/50 px-1.5 py-0.5 text-xs font-semibold text-green-300">GPU</span>
						{/if}
					</label>
						<select
							id="gen-codec"
							bind:value={codec}
							class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						>
							<option value="auto">Auto</option>
							<option value="h264">H.264</option>
							<option value="h265">H.265 (HEVC)</option>
						</select>
					</div>
				{/if}

				{#if format !== 'gif'}
					<div>
						<label for="gen-resolution" class="mb-1 block text-sm font-medium text-gray-300">Output Resolution</label>
						<select
							id="gen-resolution"
							bind:value={resolution_preset}
							onchange={onResolutionChange}
							class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						>
							<option value="original">Original</option>
							{#each Object.entries(RESOLUTION_PRESETS) as [key, dims]}
								{#if dims && dims[0] <= maxWidth && dims[1] <= maxHeight}
									<option value={key}>{key}</option>
								{/if}
							{/each}
							<option value="custom">Custom</option>
						</select>
					</div>

					{#if resolution_preset === 'custom'}
						<div class="grid grid-cols-2 gap-3">
							<div>
								<label for="gen-out-w" class="mb-1 block text-sm font-medium text-gray-300">Width</label>
								<input
									id="gen-out-w"
									type="number"
									bind:value={output_width}
									min="1"
									max={maxWidth === Infinity ? undefined : maxWidth}
									placeholder="Width"
									class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
							</div>
							<div>
								<label for="gen-out-h" class="mb-1 block text-sm font-medium text-gray-300">Height</label>
								<input
									id="gen-out-h"
									type="number"
									bind:value={output_height}
									min="1"
									max={maxHeight === Infinity ? undefined : maxHeight}
									placeholder="Height"
									class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
								/>
							</div>
						</div>
					{/if}

					<div>
						<label for="gen-quality" class="mb-1 block text-sm font-medium text-gray-300">Quality</label>
						<select
							id="gen-quality"
							bind:value={quality_preset}
							class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						>
							<option value="low">Low</option>
							<option value="medium">Medium</option>
							<option value="high">High</option>
							<option value="lossless">Lossless</option>
						</select>
					</div>
				{/if}

				<div>
					<label for="gen-deflicker" class="mb-1 block text-sm font-medium text-gray-300">Deflicker</label>
					<select
						id="gen-deflicker"
						bind:value={deflicker}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						<option value="off">Off</option>
						<option value="light">Light</option>
						<option value="medium">Medium</option>
						<option value="heavy">Heavy</option>
					</select>
				</div>

				{#if format !== 'gif'}
					<div>
						<label for="gen-motion-blur" class="mb-1 block text-sm font-medium text-gray-300">Motion Blur</label>
						<select
							id="gen-motion-blur"
							bind:value={motion_blur}
							class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						>
							<option value="off">Off</option>
							<option value="low">Low</option>
							<option value="medium">Medium</option>
							<option value="high">High</option>
						</select>
					</div>
				{/if}

				<div class="flex items-center gap-3">
					<input
						id="gen-overlay"
						type="checkbox"
						bind:checked={timestamp_overlay}
						class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
					/>
					<label for="gen-overlay" class="text-sm font-medium text-gray-300">Timestamp overlay</label>
				</div>

				<div class="flex items-center gap-3">
					<input
						id="gen-weather"
						type="checkbox"
						bind:checked={weather_overlay}
						class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
					/>
					<label for="gen-weather" class="text-sm font-medium text-gray-300">Weather overlay</label>
				</div>

				{#if weather_overlay}
					<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
						<div>
							<label for="gen-weather-pos" class="mb-1 block text-sm font-medium text-gray-300">Position</label>
							<select
								id="gen-weather-pos"
								bind:value={weather_position}
								class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="top-left">Top Left</option>
								<option value="top-right">Top Right</option>
								<option value="bottom-left">Bottom Left</option>
								<option value="bottom-right">Bottom Right</option>
							</select>
						</div>
						<div>
							<label for="gen-weather-size" class="mb-1 block text-sm font-medium text-gray-300">Font size</label>
							<input
								id="gen-weather-size"
								type="number"
								bind:value={weather_font_size}
								min="10"
								max="72"
								class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							/>
						</div>
						<div>
							<label class="mb-1 block text-sm font-medium text-gray-300">Unit</label>
							<div class="flex gap-4">
								<label class="flex items-center gap-2 text-sm text-gray-300">
									<input type="radio" bind:group={weather_unit} value="C" class="text-blue-500" />
									°C
								</label>
								<label class="flex items-center gap-2 text-sm text-gray-300">
									<input type="radio" bind:group={weather_unit} value="F" class="text-blue-500" />
									°F
								</label>
							</div>
						</div>
					</div>
				{/if}

				<div class="flex items-center gap-3">
					<input
						id="gen-heatmap"
						type="checkbox"
						bind:checked={heatmap_overlay}
						class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
					/>
					<label for="gen-heatmap" class="text-sm font-medium text-gray-300">Activity heatmap overlay</label>
				</div>

				{#if heatmap_overlay}
					<div class="space-y-3 rounded-md border border-gray-700 bg-gray-900 p-3">
						<div>
							<label for="gen-heatmap-mode" class="mb-1 block text-sm font-medium text-gray-300">Mode</label>
							<select
								id="gen-heatmap-mode"
								bind:value={heatmap_mode}
								class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="cumulative">Cumulative</option>
								<option value="sliding">Sliding window</option>
							</select>
						</div>
						<div>
							<label for="gen-heatmap-opacity" class="mb-1 block text-sm font-medium text-gray-300">Opacity: {heatmap_opacity}</label>
							<input
								id="gen-heatmap-opacity"
								type="range"
								bind:value={heatmap_opacity}
								min="0.1"
								max="0.8"
								step="0.05"
								class="w-full accent-blue-500"
							/>
						</div>
						<div>
							<label for="gen-heatmap-threshold" class="mb-1 block text-sm font-medium text-gray-300">Threshold: {heatmap_threshold}</label>
							<input
								id="gen-heatmap-threshold"
								type="range"
								bind:value={heatmap_threshold}
								min="0"
								max="50"
								step="1"
								class="w-full accent-blue-500"
							/>
							<p class="mt-0.5 text-xs text-gray-500">Filters noise — 0 = most sensitive, 50 = least sensitive</p>
						</div>
						<div>
						<label for="gen-heatmap-colormap" class="mb-1 block text-sm font-medium text-gray-300">Colormap</label>
							<select
								id="gen-heatmap-colormap"
								bind:value={heatmap_colormap}
								class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								<option value="jet">Jet</option>
								<option value="inferno">Inferno</option>
								<option value="viridis">Viridis</option>
								<option value="turbo">Turbo</option>
							</select>
						</div>
					</div>
				{/if}

				<div class="flex gap-3">
					<button
						type="button"
						onclick={onclose}
						class="flex-1 rounded-md bg-gray-700 px-4 py-2 font-medium text-gray-300 transition-colors hover:bg-gray-600"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={loading}
						class="flex-1 rounded-md bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
					>
						{loading ? 'Generating...' : 'Generate'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
