<script lang="ts">
	import { api } from '$lib/api';
	import { formatBytes } from '$lib/utils';
	import {
		activeSecondsPerDay,
		framesPerDay,
		bytesPerMonth,
		daysUntilFull,
		scaleFrameSize,
		formatCount
	} from '$lib/estimates';

	interface Props {
		intervalSeconds: number;
		captureMode?: string;
		activeStart?: string | null;
		activeEnd?: string | null;
		sunEvents?: string[];
		resolutionWidth?: number | null;
		resolutionHeight?: number | null;
		/** Existing plan: its own frames are the best basis there is. */
		profileId?: number | null;
		/** New camera: a frame from the source test, as a fallback basis. */
		sampleBytes?: number | null;
		sampleWidth?: number | null;
		sampleHeight?: number | null;
	}

	let {
		intervalSeconds,
		captureMode = 'always',
		activeStart = null,
		activeEnd = null,
		sunEvents = [],
		resolutionWidth = null,
		resolutionHeight = null,
		profileId = null,
		sampleBytes = null,
		sampleWidth = null,
		sampleHeight = null
	}: Props = $props();

	let measuredBytes = $state<number | null>(null);
	let measuredCount = $state(0);
	let freeBytes = $state<number | null>(null);

	$effect(() => {
		const id = profileId;
		if (!id) {
			measuredBytes = null;
			measuredCount = 0;
			return;
		}
		api.countCaptures(id)
			.then((r) => {
				measuredBytes = r.avg_bytes;
				measuredCount = r.count;
			})
			.catch(() => {
				measuredBytes = null;
			});
	});

	$effect(() => {
		api.getStorage().then((s) => { freeBytes = s.disk_free_bytes; }).catch(() => {});
	});

	let window = $derived(
		activeSecondsPerDay(captureMode, activeStart, activeEnd, sunEvents)
	);
	let frames = $derived(window ? framesPerDay(window.seconds, intervalSeconds) : 0);

	// Prefer what this plan actually produces over a sample of one. The sample
	// is scaled to the chosen output size, since that is the one correction we
	// can make honestly.
	let frameBytes = $derived.by(() => {
		if (measuredBytes) return { bytes: measuredBytes, basis: 'measured' as const };
		if (sampleBytes) {
			return {
				bytes: scaleFrameSize(
					sampleBytes,
					sampleWidth,
					sampleHeight,
					resolutionWidth,
					resolutionHeight
				),
				basis: 'sampled' as const
			};
		}
		return null;
	});

	let perMonth = $derived(frameBytes ? bytesPerMonth(frames, frameBytes.bytes) : null);
	let fillDays = $derived(
		frameBytes && freeBytes ? daysUntilFull(frames, frameBytes.bytes, freeBytes) : null
	);
</script>

{#if window && frames > 0}
	<div class="rounded-md border border-gray-700 bg-gray-900/60 px-3 py-2 text-xs">
		<p class="text-gray-300">
			<span class="font-semibold text-gray-100">{formatCount(frames)}</span> frames/day
			{#if perMonth}
				· <span class="font-semibold text-gray-100">~{formatBytes(perMonth)}</span>/month
			{/if}
		</p>

		<p class="mt-1 text-gray-500">
			{#if frameBytes?.basis === 'measured'}
				Based on this plan's {formatCount(measuredCount)} existing frames.
			{:else if frameBytes?.basis === 'sampled'}
				Storage estimated from one test frame — the real figure depends on how much
				the scene moves.
			{:else}
				Capture a few frames to get a storage estimate.
			{/if}
			{#if window.approximate && window.caveat}
				<span class="text-amber-400">Window is an {window.caveat}.</span>
			{/if}
		</p>

		{#if fillDays !== null && fillDays < 120}
			<p class="mt-1 {fillDays < 30 ? 'text-red-400' : 'text-amber-400'}">
				At this rate the disk fills in about {formatCount(fillDays)} days. Consider a
				cleanup schedule in Settings → Data Cleanup.
			</p>
		{/if}
	</div>
{/if}
