<script lang="ts">
	import { api } from '$lib/api';
	import type { StreamDiagnostics } from '$lib/types';

	interface Props {
		streamId: number;
		/** Bump after anything that could change the chain (toggling a plan, saving). */
		refreshKey?: number;
	}

	let { streamId, refreshKey = 0 }: Props = $props();

	let data = $state<StreamDiagnostics | null>(null);
	let failed = $state(false);

	function load() {
		api.getStreamDiagnostics(streamId)
			.then((d) => {
				data = d;
				failed = false;
			})
			.catch(() => {
				failed = true;
			});
	}

	$effect(() => {
		streamId;
		refreshKey;
		load();
	});

	// The answer changes on its own — a window opens, frames go stale — so keep
	// it current without making the user reload. Skipped while the tab is hidden.
	$effect(() => {
		const timer = setInterval(() => {
			if (!document.hidden) load();
		}, 30000);
		return () => clearInterval(timer);
	});

	const TONE = {
		ok: { dot: 'bg-green-500', text: 'text-green-300', ring: 'border-green-900 bg-green-950/30' },
		idle: { dot: 'bg-amber-500', text: 'text-amber-300', ring: 'border-amber-900 bg-amber-950/30' },
		fail: { dot: 'bg-red-500', text: 'text-red-300', ring: 'border-red-900 bg-red-950/30' }
	} as const;

	const CHECK_TONE = {
		ok: 'text-green-400',
		warn: 'text-amber-400',
		idle: 'text-amber-400',
		fail: 'text-red-400'
	} as const;

	let tone = $derived(data ? TONE[data.status] : null);
</script>

{#if data && tone}
	<div class="rounded-xl border {tone.ring} p-4">
		<details>
			<summary
				class="flex cursor-pointer list-none items-center gap-3 marker:content-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
			>
				<span class="h-2.5 w-2.5 shrink-0 rounded-full {tone.dot}"></span>
				<span class="flex-1 text-sm font-medium {tone.text}">{data.summary}</span>
				<svg
					class="chevron h-4 w-4 shrink-0 text-gray-500"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
				</svg>
			</summary>

			<ul class="mt-3 space-y-1.5 border-t border-gray-800 pt-3">
				{#each data.checks as check (check.key)}
					<li class="flex items-start gap-2 text-xs">
						<span class="mt-0.5 shrink-0 {CHECK_TONE[check.state]}">
							{#if check.state === 'ok'}✓{:else if check.state === 'fail'}✕{:else}•{/if}
						</span>
						<span class="text-gray-300">{check.label}</span>
						{#if check.detail}
							<span class="text-gray-500">— {check.detail}</span>
						{/if}
					</li>
				{/each}
			</ul>
		</details>
	</div>
{:else if failed}
	<p class="text-xs text-gray-600">Could not load the capture status for this camera.</p>
{/if}

<style>
	details[open] .chevron {
		transform: rotate(90deg);
	}
	.chevron {
		transition: transform 150ms ease;
	}
	@media (prefers-reduced-motion: reduce) {
		.chevron {
			transition: none;
		}
	}
	summary::-webkit-details-marker {
		display: none;
	}
</style>
