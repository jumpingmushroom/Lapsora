<script lang="ts">
	import { api } from '$lib/api';
	import { defaultCapturePlanDraft, capturePlanComplete, capturePlanPayload } from '$lib/capturePlan';
	import type { CapturePlanDraft } from '$lib/capturePlan';
	import CapturePlanStep from './CapturePlanStep.svelte';
	import RenderScheduleStep from './RenderScheduleStep.svelte';

	interface Props {
		streamId: number;
		cameraName: string;
		onclose: () => void;
		/** Called once something was created, so the page can refetch. */
		oncreated: () => void;
	}

	let { streamId, cameraName, onclose, oncreated }: Props = $props();

	let step = $state(1);
	let plan = $state<CapturePlanDraft>(defaultCapturePlanDraft());
	let scheduleChoice = $state('daily');
	let creating = $state(false);
	let createError = $state('');

	let planComplete = $derived(capturePlanComplete(plan));

	// A live frame gives the storage estimate a real basis. Without it the
	// estimate still shows frames/day and says plainly that it can't price
	// them — better than inventing a number. Failure here is silent by design.
	let sampleBytes = $state<number | null>(null);
	let sampleWidth = $state<number | null>(null);
	let sampleHeight = $state<number | null>(null);

	$effect(() => {
		let objectUrl: string | null = null;
		let cancelled = false;

		fetch(api.getStreamPreviewUrl(streamId))
			.then((r) => (r.ok ? r.blob() : Promise.reject(new Error('no preview'))))
			.then((blob) => {
				if (cancelled) return;
				objectUrl = URL.createObjectURL(blob);
				const img = new Image();
				img.onload = () => {
					if (!cancelled) {
						sampleBytes = blob.size;
						sampleWidth = img.naturalWidth;
						sampleHeight = img.naturalHeight;
					}
					if (objectUrl) URL.revokeObjectURL(objectUrl);
				};
				img.onerror = () => {
					if (objectUrl) URL.revokeObjectURL(objectUrl);
				};
				img.src = objectUrl;
			})
			.catch(() => {});

		return () => {
			cancelled = true;
			if (objectUrl) URL.revokeObjectURL(objectUrl);
		};
	});

	async function finish() {
		creating = true;
		createError = '';
		let profileId: number | null = null;
		try {
			const profile = plan.custom
				? await api.createProfile(streamId, capturePlanPayload(plan))
				: await api.applyProfileTemplate(plan.presetId!, streamId, plan.name);
			profileId = profile.id;

			if (scheduleChoice !== 'none') {
				await api.createTimelapseSchedule({
					profile_id: profileId,
					preset: scheduleChoice,
					name: scheduleChoice === 'daily' ? 'Daily' : 'Weekly'
				});
			}

			oncreated();
			onclose();
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Something went wrong';
			// Two endpoints, no transaction. Say what exists rather than
			// silently deleting the plan that was just made.
			if (profileId) {
				createError = `The capture plan was created, but the render schedule wasn't: ${message}.`;
				oncreated();
			} else {
				createError = `Could not create the capture plan: ${message}`;
			}
			creating = false;
		}
	}
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
			<div class="mb-3 flex items-center justify-between">
				<h2 class="text-lg font-semibold text-gray-100">Add capture plan</h2>
				<button onclick={onclose} aria-label="Close" class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<ol class="flex items-center gap-2 text-xs">
				{#each ['Plan', 'Render'] as title, i}
					{@const n = i + 1}
					<li class="flex items-center gap-2">
						<span
							class="flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold {
								step > n ? 'bg-green-900 text-green-300'
								: step === n ? 'bg-blue-600 text-white'
								: 'bg-gray-800 text-gray-500'
							}"
						>{step > n ? '✓' : n}</span>
						<span class={step === n ? 'font-medium text-gray-200' : 'text-gray-500'}>{title}</span>
					</li>
					{#if n < 2}
						<li aria-hidden="true" class="h-px w-6 bg-gray-700"></li>
					{/if}
				{/each}
			</ol>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto p-4">
			{#if step === 1}
				<CapturePlanStep
					bind:value={plan}
					{cameraName}
					{sampleBytes}
					{sampleWidth}
					{sampleHeight}
					idPrefix="addplan"
				/>
			{:else}
				<RenderScheduleStep
					bind:value={scheduleChoice}
					intro="Rendering turns {plan.name || 'this plan'}'s frames into a video. You can change or add schedules later."
				/>

				{#if createError}
					<p class="rounded-lg border border-red-800 bg-red-950/50 px-3 py-2 text-sm text-red-300">{createError}</p>
				{/if}
			{/if}
		</div>

		<div class="flex shrink-0 items-center justify-between border-t border-gray-800 p-4">
			{#if step === 2}
				<button
					onclick={() => { step = 1; }}
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
				{#if step === 1}
					<button
						onclick={() => { step = 2; }}
						disabled={!planComplete}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
					>
						Next
					</button>
				{:else}
					<button
						onclick={finish}
						disabled={creating}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{creating ? 'Creating…' : 'Create plan'}
					</button>
				{/if}
			</div>
		</div>
	</div>
</div>
