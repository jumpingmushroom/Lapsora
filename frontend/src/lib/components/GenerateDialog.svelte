<script lang="ts">
	import { api } from '$lib/api';
	import { localToUtcNaive } from '$lib/utils';
	import { renderOptionsForProfile, renderOptionsPayload } from '$lib/renderOptions';
	import type { Profile, RenderOptionsValue } from '$lib/types';
	import RenderOptions from './RenderOptions.svelte';

	interface Props {
		profileOptions: { id: number; label: string; resolution_width: number | null; resolution_height: number | null }[];
		open: boolean;
		onclose: () => void;
	}

	let { profileOptions, open, onclose }: Props = $props();
	let selectedProfileId = $state(profileOptions[0]?.id ?? 0);

	type Preset = 'last1h' | 'last24h' | 'today' | 'yesterday' | 'last7d' | 'last30d' | 'thisWeek' | 'lastWeek' | 'custom';

	const PRESETS: { key: Preset; label: string }[] = [
		{ key: 'last1h', label: 'Last 1h' },
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
			case 'last1h':
				start = new Date(now.getTime() - 60 * 60 * 1000);
				break;
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

	// Captures are stored in UTC, and the presets above serialize via
	// toISOString() (UTC). The custom inputs are local wall-clock, so convert
	// them to UTC too (localToUtcNaive) — otherwise a non-UTC user's custom
	// range is shifted by their offset and selects the wrong frames (or none).
	let period_start = $derived.by(() => {
		if (selectedPreset === 'custom') {
			if (!customStartDate) return '';
			return localToUtcNaive(customStartDate, customStartTime || '00:00');
		}
		return computePresetRange(selectedPreset)?.start ?? '';
	});

	let period_end = $derived.by(() => {
		if (selectedPreset === 'custom') {
			if (!customEndDate) return '';
			return localToUtcNaive(customEndDate, customEndTime || '23:59');
		}
		return computePresetRange(selectedPreset)?.end ?? '';
	});

	let options = $state<RenderOptionsValue>(renderOptionsForProfile(undefined));
	let loading = $state(false);
	let error = $state('');

	let selectedProfile = $derived(profileOptions.find(p => p.id === selectedProfileId));
	let maxWidth = $derived(selectedProfile?.resolution_width ?? Infinity);
	let maxHeight = $derived(selectedProfile?.resolution_height ?? Infinity);

	// Seed the render settings from the chosen plan's own defaults, which it
	// carries from the plan preset it was created from. Re-seeded when the plan
	// changes, since a different plan can encode a different intent.
	let seededFor = $state<number | null>(null);
	$effect(() => {
		const id = selectedProfileId;
		if (!id || seededFor === id) return;
		seededFor = id;
		api.getProfile(id)
			.then((profile: Profile) => {
				if (selectedProfileId === id) options = renderOptionsForProfile(profile);
			})
			.catch(() => {
				if (selectedProfileId === id) options = renderOptionsForProfile(undefined);
			});
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		loading = true;
		error = '';
		// A malformed or incomplete custom range converts to '' and would
		// otherwise submit as an unbounded (whole-history) generation. Catch it
		// here. A fully-empty custom range is still allowed (means "all frames").
		if (selectedPreset === 'custom') {
			if ((customStartDate || customStartTime) && !period_start) {
				error = 'Enter a valid start date and time (HH:MM).';
				loading = false;
				return;
			}
			if ((customEndDate || customEndTime) && !period_end) {
				error = 'Enter a valid end date and time (HH:MM).';
				loading = false;
				return;
			}
		}
		try {
			await api.generateTimelapse(selectedProfileId, {
				period_start: period_start || undefined,
				period_end: period_end || undefined,
				...renderOptionsPayload(options)
			});
			onclose();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Render failed';
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
		<div class="flex max-h-[90vh] w-full max-w-md flex-col rounded-lg bg-gray-800 p-6">
			<h2 class="mb-4 shrink-0 text-xl font-semibold text-gray-100">Render timelapse</h2>

			{#if error}
				<p class="mb-3 rounded-md bg-red-900/50 px-3 py-2 text-sm text-red-300">{error}</p>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4 overflow-y-auto">
				<RenderOptions bind:value={options} {maxWidth} {maxHeight} idPrefix="gen">
					{#snippet basics()}
						<div>
							<label for="gen-profile" class="mb-1 block text-sm font-medium text-gray-300">Capture plan</label>
							<select
								id="gen-profile"
								bind:value={selectedProfileId}
								class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							>
								{#each profileOptions as opt}
									<option value={opt.id}>{opt.label}</option>
								{/each}
							</select>
						</div>

						<div>
							<span class="mb-1.5 block text-sm font-medium text-gray-300">Time range</span>
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
											class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
										/>
										<input
											id="gen-start-time"
											type="text"
											bind:value={customStartTime}
											class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
											class="flex-1 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
										/>
										<input
											id="gen-end-time"
											type="text"
											bind:value={customEndTime}
											class="w-28 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
										/>
									</div>
								</div>
							</div>
						{/if}
					{/snippet}
				</RenderOptions>

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
						{loading ? 'Rendering...' : 'Render'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
