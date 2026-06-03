<script lang="ts">
	import { api } from '$lib/api';
	import { formatDateTime, formatBytes } from '$lib/utils';
	import type { Capture } from '$lib/types';

	interface Props {
		captures: Capture[];
		index: number;
		allLoaded: boolean;
		onLoadMore: () => void;
		onClose: () => void;
	}

	let { captures, index = $bindable(), allLoaded, onLoadMore, onClose }: Props = $props();

	let current = $derived(captures[index]);
	let imgLoading = $state(true);

	let hasPrev = $derived(index > 0);
	let hasNext = $derived(index < captures.length - 1);

	let thumbEls = $state<HTMLElement[]>([]);

	function prev() {
		if (hasPrev) index -= 1;
	}
	function next() {
		if (hasNext) index += 1;
	}
	function handleKey(e: KeyboardEvent) {
		if (e.key === 'ArrowLeft') prev();
		else if (e.key === 'ArrowRight') next();
		else if (e.key === 'Escape') onClose();
	}

	// Show the spinner again whenever the displayed capture changes.
	$effect(() => {
		current.id;
		imgLoading = true;
	});

	// Fetch older captures as we approach the end of the loaded set.
	$effect(() => {
		if (index >= captures.length - 2 && !allLoaded) onLoadMore();
	});

	// Keep the active filmstrip thumbnail in view.
	$effect(() => {
		thumbEls[index]?.scrollIntoView({ inline: 'center', block: 'nearest' });
	});
</script>

<svelte:window onkeydown={handleKey} />

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm"
	onclick={onClose}
>
	<!-- Top bar -->
	<div class="flex items-center justify-between px-4 py-3" onclick={(e) => e.stopPropagation()}>
		<span class="text-sm text-gray-400">{index + 1} / {captures.length}{allLoaded ? '' : '+'}</span>
		<button
			type="button"
			onclick={onClose}
			class="flex h-9 w-9 items-center justify-center rounded-full bg-gray-800/80 text-gray-200 hover:bg-gray-700"
			aria-label="Close preview"
		>✕</button>
	</div>

	<!-- Image stage -->
	<div class="relative flex min-h-0 flex-1 items-center justify-center px-4">
		<!-- Prev -->
		<button
			type="button"
			onclick={(e) => { e.stopPropagation(); prev(); }}
			disabled={!hasPrev}
			class="absolute left-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-black/55 text-2xl text-white transition hover:bg-black/75 disabled:cursor-default disabled:opacity-25"
			aria-label="Previous capture"
		>‹</button>

		<div class="relative flex h-full w-full items-center justify-center" onclick={(e) => e.stopPropagation()}>
			{#if imgLoading}
				<div class="absolute h-10 w-10 animate-spin rounded-full border-2 border-gray-600 border-t-blue-500"></div>
			{/if}
			{#key current.id}
				<img
					src={api.getCaptureImageUrl(current.id)}
					alt="Capture {current.id}"
					class="max-h-full max-w-full object-contain"
					onload={() => (imgLoading = false)}
					onerror={() => (imgLoading = false)}
				/>
			{/key}

			<!-- Caption bar -->
			<div class="pointer-events-none absolute inset-x-0 bottom-0 flex flex-wrap items-center justify-between gap-2 bg-gradient-to-t from-black/85 to-transparent px-4 pb-4 pt-10">
				<span class="rounded-full bg-black/70 px-3 py-1 text-sm font-semibold text-gray-100">
					{formatDateTime(current.captured_at)}
				</span>
				<span class="flex items-center gap-2 text-xs text-gray-300">
					{#if current.width && current.height}
						<span>{current.width}×{current.height}</span>
					{/if}
					{#if current.file_size != null}
						<span class="text-gray-500">·</span>
						<span>{formatBytes(current.file_size)}</span>
					{/if}
					{#if current.is_hdr}
						<span class="rounded bg-blue-600 px-1.5 py-0.5 text-[10px] font-bold text-white">HDR</span>
					{/if}
					{#if current.weather_temp != null}
						<span class="text-gray-500">·</span>
						<span>{current.weather_temp.toFixed(1)}°C</span>
					{/if}
				</span>
			</div>
		</div>

		<!-- Next -->
		<button
			type="button"
			onclick={(e) => { e.stopPropagation(); next(); }}
			disabled={!hasNext}
			class="absolute right-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-black/55 text-2xl text-white transition hover:bg-black/75 disabled:cursor-default disabled:opacity-25"
			aria-label="Next capture"
		>›</button>
	</div>

	<!-- Filmstrip -->
	<div class="flex gap-2 overflow-x-auto px-4 py-3" onclick={(e) => e.stopPropagation()}>
		{#each captures as capture, i}
			<button
				type="button"
				bind:this={thumbEls[i]}
				onclick={() => (index = i)}
				class="relative h-14 w-20 flex-shrink-0 overflow-hidden rounded-md bg-gray-800 transition {i === index ? 'ring-2 ring-blue-500' : 'opacity-60 hover:opacity-100'}"
				aria-label="View capture {i + 1}"
			>
				<img
					src={api.getCaptureImageUrl(capture.id)}
					alt="Capture {capture.id}"
					class="h-full w-full object-cover"
					loading="lazy"
				/>
			</button>
		{/each}
	</div>
</div>
