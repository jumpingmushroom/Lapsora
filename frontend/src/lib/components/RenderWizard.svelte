<script lang="ts">
	import { api } from '$lib/api';
	import { renderOptionsPayload, renderOptionsForProfile } from '$lib/renderOptions';
	import {
		RANGE_PRESETS,
		SCHEDULE_PRESETS,
		defaultRenderDraft,
		draftRangeStart,
		draftRangeEnd,
		renderDraftError
	} from '$lib/renderDraft';
	import type { RenderDraft, RenderMode } from '$lib/renderDraft';
	import { activeSecondsPerDay, framesPerDay } from '$lib/estimates';
	import type { Profile, Stream } from '$lib/types';
	import RenderOptions from './RenderOptions.svelte';

	interface Props {
		/** Prefilled draft. Create flows pass a default; edit passes the schedule. */
		draft: RenderDraft;
		/** 'edit' drops the stepping and shows everything at once — a form. */
		mode?: 'create' | 'edit';
		/** Set when editing an existing schedule. */
		scheduleId?: number | null;
		/** True when the plan is implied by where this was opened from. */
		planFixed?: boolean;
		/** Restrict the branch choice; omit to offer both. */
		lockMode?: RenderMode | null;
		/** Narrow the plan picker, e.g. to one camera's plans. */
		allowedProfileIds?: number[] | null;
		onclose: () => void;
		ondone: () => void;
	}

	let {
		draft,
		mode = 'create',
		scheduleId = null,
		planFixed = false,
		lockMode = null,
		allowedProfileIds = null,
		onclose,
		ondone
	}: Props = $props();

	let d = $state<RenderDraft>(draft);
	// With the plan already implied there is nothing to ask on step 1.
	let step = $state(planFixed ? 2 : 1);
	let submitting = $state(false);
	let error = $state('');

	let streams = $state<Stream[]>([]);
	let profiles = $state<Profile[]>([]);

	$effect(() => {
		Promise.all([api.getStreams(), api.getAllProfiles()])
			.then(([s, p]) => {
				streams = s;
				profiles = allowedProfileIds ? p.filter((x) => allowedProfileIds.includes(x.id)) : p;
				if (!d.profileId && profiles.length) d.profileId = profiles[0].id;
			})
			.catch(() => {});
	});

	let selectedProfile = $derived(profiles.find((p) => p.id === d.profileId));
	let maxWidth = $derived(selectedProfile?.resolution_width ?? Infinity);
	let maxHeight = $derived(selectedProfile?.resolution_height ?? Infinity);

	// Seed render settings from the plan's own defaults, but never clobber a
	// schedule being edited or a draft the user has already touched.
	let seededFor = $state<number | null>(null);
	$effect(() => {
		const id = d.profileId;
		if (mode === 'edit' || !id || seededFor === id) return;
		const profile = profiles.find((p) => p.id === id);
		if (!profile) return;
		if (seededFor !== null) d.options = renderOptionsForProfile(profile);
		seededFor = id;
	});

	// --- frame count: counted for a one-shot, derived for a schedule ---
	let frameCount = $state<number | null>(null);
	let frameCountApproximate = $derived(d.mode === 'repeat');

	$effect(() => {
		const id = d.profileId;
		const isOnce = d.mode === 'once';
		const start = isOnce ? draftRangeStart(d) : '';
		const end = isOnce ? draftRangeEnd(d) : '';
		const lookback = d.lookbackHours;
		const plan = profiles.find((p) => p.id === id);

		if (!id) {
			frameCount = null;
			return;
		}

		if (!isOnce) {
			// A schedule has no fixed range, so derive from interval and active
			// hours over the lookback window.
			if (!plan || !lookback) {
				frameCount = null;
				return;
			}
			const window = activeSecondsPerDay(
				plan.capture_mode,
				plan.active_start_time,
				plan.active_end_time,
				plan.sun_events ? plan.sun_events.split(',').filter(Boolean) : []
			);
			frameCount = window
				? Math.floor((framesPerDay(window.seconds, plan.interval_seconds) * lookback) / 24)
				: null;
			return;
		}

		let cancelled = false;
		// Debounced: the custom date inputs fire on every keystroke.
		const timer = setTimeout(() => {
			api.countCaptures(id, start || undefined, end || undefined)
				.then((r) => { if (!cancelled) frameCount = r.count; })
				.catch(() => { if (!cancelled) frameCount = null; });
		}, 250);
		return () => { cancelled = true; clearTimeout(timer); };
	});

	function selectSchedulePreset(key: string) {
		d.schedulePreset = key;
		d.cron = SCHEDULE_PRESETS[key].cron;
		d.cronCustom = false;
		d.lookbackHours = SCHEDULE_PRESETS[key].lookback;
		if (!d.name.trim()) d.name = SCHEDULE_PRESETS[key].label;
	}

	function selectCustomCron() {
		d.schedulePreset = null;
		d.cron = '';
		d.cronCustom = true;
		d.lookbackHours = null;
		if (!d.name.trim()) d.name = 'Custom';
	}

	let validationError = $derived(renderDraftError(d));

	async function submit() {
		const problem = renderDraftError(d);
		if (problem) {
			error = problem;
			return;
		}
		submitting = true;
		error = '';
		try {
			if (d.mode === 'once') {
				await api.generateTimelapse(d.profileId, {
					period_start: draftRangeStart(d) || undefined,
					period_end: draftRangeEnd(d) || undefined,
					...renderOptionsPayload(d.options)
				});
			} else if (scheduleId) {
				await api.updateTimelapseSchedule(scheduleId, {
					name: d.name,
					preset: d.schedulePreset,
					cron_expression: d.cronCustom ? d.cron : undefined,
					// Sent even when null so clearing the field actually clears it.
					lookback_hours: d.lookbackHours,
					...d.options
				});
			} else {
				await api.createTimelapseSchedule({
					profile_id: d.profileId,
					name: d.name,
					preset: d.schedulePreset,
					cron_expression: d.cronCustom ? d.cron : undefined,
					lookback_hours: d.lookbackHours ?? undefined,
					...d.options
				});
			}
			ondone();
			onclose();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to save';
			submitting = false;
		}
	}

	const flat = $derived(mode === 'edit');
	const steps = $derived(planFixed ? ['When', 'How'] : ['What', 'When', 'How']);

	const fieldClass =
		'w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
	const labelClass = 'mb-1 block text-sm font-medium text-gray-300';

	let title = $derived(
		flat ? 'Edit render schedule' : d.mode === 'once' ? 'Render timelapse' : 'Add render schedule'
	);
	let submitLabel = $derived(
		flat ? 'Save schedule' : d.mode === 'once' ? 'Render' : 'Create schedule'
	);
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') onclose(); }} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
	onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}
>
	<div class="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl bg-gray-900 shadow-xl">
		<div class="shrink-0 border-b border-gray-800 p-4">
			<div class="flex items-center justify-between {flat ? '' : 'mb-3'}">
				<h2 class="text-lg font-semibold text-gray-100">{title}</h2>
				<button onclick={onclose} aria-label="Close" class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			{#if !flat}
				<ol class="flex items-center gap-2 text-xs">
					{#each steps as label, i}
						{@const n = i + (planFixed ? 2 : 1)}
						<li class="flex items-center gap-2">
							<span
								class="flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold {
									step > n ? 'bg-green-900 text-green-300'
									: step === n ? 'bg-blue-600 text-white'
									: 'bg-gray-800 text-gray-500'
								}"
							>{step > n ? '✓' : i + 1}</span>
							<span class={step === n ? 'font-medium text-gray-200' : 'text-gray-500'}>{label}</span>
						</li>
						{#if i < steps.length - 1}
							<li aria-hidden="true" class="h-px w-6 bg-gray-700"></li>
						{/if}
					{/each}
				</ol>
			{/if}
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto p-4">
			<!-- ── What ── -->
			{#if flat || step === 1}
				{#if !planFixed}
					<div>
						<label for="rw-plan" class={labelClass}>Capture plan</label>
						<select id="rw-plan" bind:value={d.profileId} disabled={flat} class="{fieldClass} disabled:opacity-50">
							{#each streams as stream}
								<optgroup label={stream.name}>
									{#each profiles.filter((p) => p.stream_id === stream.id) as p}
										<option value={p.id}>{p.name}</option>
									{/each}
								</optgroup>
							{/each}
						</select>
					</div>
				{/if}
			{/if}

			<!-- ── When ── -->
			{#if flat || step === 2}
				{#if !lockMode && !flat}
					<div>
						<span class={labelClass}>How often?</span>
						<div class="grid grid-cols-2 gap-2">
							<button
								type="button"
								onclick={() => { d.mode = 'once'; }}
								class="rounded-lg border p-3 text-left transition-colors {d.mode === 'once' ? 'border-blue-500 bg-blue-950/40' : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'}"
							>
								<span class="block text-sm font-medium text-gray-100">Just once</span>
								<span class="mt-0.5 block text-xs text-gray-500">Render a range now</span>
							</button>
							<button
								type="button"
								onclick={() => { d.mode = 'repeat'; if (!d.schedulePreset && !d.cronCustom) selectSchedulePreset('daily'); }}
								class="rounded-lg border p-3 text-left transition-colors {d.mode === 'repeat' ? 'border-blue-500 bg-blue-950/40' : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'}"
							>
								<span class="block text-sm font-medium text-gray-100">On a schedule</span>
								<span class="mt-0.5 block text-xs text-gray-500">Repeat automatically</span>
							</button>
						</div>
					</div>
				{/if}

				{#if d.mode === 'once'}
					<div>
						<span class={labelClass}>Time range</span>
						<div class="flex flex-wrap gap-1.5">
							{#each RANGE_PRESETS as preset}
								<button
									type="button"
									onclick={() => { d.rangePreset = preset.key; }}
									class="rounded-full px-3 py-1 text-xs font-medium transition-colors {d.rangePreset === preset.key ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}"
								>{preset.label}</button>
							{/each}
						</div>
					</div>

					{#if d.rangePreset === 'custom'}
						<div class="space-y-3 rounded-lg border border-gray-700 bg-gray-800/50 p-3">
							<div>
								<label for="rw-start-date" class={labelClass}>Start</label>
								<div class="flex gap-2">
									<input id="rw-start-date" type="date" bind:value={d.customStartDate} class="{fieldClass} flex-1" />
									<input id="rw-start-time" type="text" bind:value={d.customStartTime} class="{fieldClass} w-28" />
								</div>
							</div>
							<div>
								<label for="rw-end-date" class={labelClass}>End</label>
								<div class="flex gap-2">
									<input id="rw-end-date" type="date" bind:value={d.customEndDate} class="{fieldClass} flex-1" />
									<input id="rw-end-time" type="text" bind:value={d.customEndTime} class="{fieldClass} w-28" />
								</div>
							</div>
						</div>
					{/if}
				{:else}
					<div>
						<span class={labelClass}>How often</span>
						<div class="grid grid-cols-3 gap-2 sm:grid-cols-5">
							{#each Object.entries(SCHEDULE_PRESETS) as [key, info]}
								<button
									type="button"
									onclick={() => selectSchedulePreset(key)}
									class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors {d.schedulePreset === key ? 'border-blue-500 bg-blue-600 text-white' : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'}"
								>{info.label}</button>
							{/each}
							<button
								type="button"
								onclick={selectCustomCron}
								class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors {d.cronCustom ? 'border-blue-500 bg-blue-600 text-white' : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600'}"
							>Custom</button>
						</div>
					</div>

					{#if d.cronCustom}
						<div>
							<label for="rw-cron" class={labelClass}>Cron expression</label>
							<input id="rw-cron" type="text" bind:value={d.cron} placeholder="*/5 * * * *" class={fieldClass} />
							<p class="mt-1 text-xs text-gray-500">Format: minute hour day month weekday</p>
						</div>
					{/if}

					{#if d.schedulePreset || d.cronCustom}
						<div>
							<label for="rw-lookback" class={labelClass}>Lookback window (hours)</label>
							<input
								id="rw-lookback"
								type="number"
								bind:value={d.lookbackHours}
								min="1"
								placeholder={d.schedulePreset ? String(SCHEDULE_PRESETS[d.schedulePreset]?.lookback ?? '') : 'e.g. 1 for hourly'}
								class={fieldClass}
							/>
							<p class="mt-1 text-xs text-gray-500">
								{#if d.lookbackHours}
									Captures from the last {d.lookbackHours}h ({d.lookbackHours >= 24 ? `${Math.round(d.lookbackHours / 24)} days` : `${d.lookbackHours} hours`})
								{:else}
									How far back to include captures
								{/if}
							</p>
						</div>

						<div>
							<label for="rw-name" class={labelClass}>Name</label>
							<input id="rw-name" type="text" bind:value={d.name} class={fieldClass} />
						</div>
					{/if}
				{/if}
			{/if}

			<!-- ── How ── -->
			{#if flat || step === 3}
				<RenderOptions
					bind:value={d.options}
					{maxWidth}
					{maxHeight}
					idPrefix="rw"
					{frameCount}
					{frameCountApproximate}
				/>
			{/if}

			{#if error}
				<p class="rounded-lg border border-red-800 bg-red-950/50 px-3 py-2 text-sm text-red-300">{error}</p>
			{/if}
		</div>

		<div class="flex shrink-0 items-center justify-between border-t border-gray-800 p-4">
			{#if !flat && step > (planFixed ? 2 : 1)}
				<button
					onclick={() => { step -= 1; }}
					class="rounded-lg px-3 py-2 text-sm font-medium text-gray-400 hover:text-gray-200"
				>
					Back
				</button>
			{:else}
				<span></span>
			{/if}

			<div class="flex gap-2">
				<button onclick={onclose} class="rounded-lg px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200">
					Cancel
				</button>
				{#if !flat && step < 3}
					<button
						onclick={() => { step += 1; }}
						disabled={step === 1 && !d.profileId}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
					>
						Next
					</button>
				{:else}
					<button
						onclick={submit}
						disabled={submitting || !!validationError}
						title={validationError ?? undefined}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{submitting ? 'Working…' : submitLabel}
					</button>
				{/if}
			</div>
		</div>
	</div>
</div>
