<script lang="ts">
	import { api } from '$lib/api';
	import { formatDateTime, formatFinishedAt, formatDuration } from '$lib/utils';
	import type { PrintJob, Timelapse } from '$lib/types';
	import TimelapsePlayer from './TimelapsePlayer.svelte';

	interface Props {
		streamId: number;
		/** Bump to refetch. */
		refreshKey?: number;
	}

	let { streamId, refreshKey = 0 }: Props = $props();

	let jobs = $state<PrintJob[]>([]);
	let loaded = $state(false);
	let selected = $state<Timelapse | null>(null);

	let deleteTarget = $state<PrintJob | null>(null);
	let deleteWithTimelapse = $state(false);
	let deleting = $state(false);

	function load() {
		api.getPrintJobs(streamId)
			.then((j) => { jobs = j; loaded = true; })
			.catch(() => { jobs = []; loaded = true; });
	}

	$effect(() => {
		streamId;
		refreshKey;
		load();
	});

	// Prints finish while the page is open, and the list is the only place that
	// shows it. Cheap enough to re-ask; skipped while the tab is hidden.
	$effect(() => {
		const timer = setInterval(() => {
			if (!document.hidden) load();
		}, 30000);
		return () => clearInterval(timer);
	});

	function duration(job: PrintJob): string {
		if (!job.finished_at) return '—';
		const secs =
			(new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000;
		return formatDuration(secs);
	}

	async function play(job: PrintJob) {
		if (!job.timelapse_id) return;
		try {
			selected = await api.getTimelapse(job.timelapse_id);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to load the video');
		}
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleting = true;
		const target = deleteTarget;
		try {
			await api.deletePrintJob(target.id, deleteWithTimelapse);
			jobs = jobs.filter((j) => j.id !== target.id);
			deleteTarget = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Delete failed');
		} finally {
			deleting = false;
		}
	}
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key !== 'Escape') return;
		if (deleteTarget) deleteTarget = null;
		else if (selected) selected = null;
	}}
/>

<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
	<div class="mb-1 flex items-center justify-between">
		<h2 class="text-lg font-semibold text-gray-100">Prints</h2>
		<a href="/settings" class="text-xs text-blue-400 hover:text-blue-300">Printer settings →</a>
	</div>
	<p class="mb-4 text-xs text-gray-500">
		Each print is filmed automatically and rendered when it finishes. Clip length, frame rate
		and overlays are set in Settings → 3D Printing.
	</p>

	{#if !loaded}
		<p class="text-sm text-gray-500">Loading…</p>
	{:else if jobs.length === 0}
		<div class="rounded-lg border border-gray-800 bg-gray-800/40 p-4">
			<p class="text-sm text-gray-400">No prints recorded yet.</p>
			<p class="mt-1 text-xs text-gray-500">
				Lapsora starts capturing when PrusaLink reports a print starting, and renders the
				video when it finishes.
			</p>
		</div>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-left text-sm">
				<thead>
					<tr class="border-b border-gray-800 text-gray-400">
						<th class="py-2 pr-4 font-medium">Print</th>
						<th class="py-2 pr-4 font-medium">Status</th>
						<th class="py-2 pr-4 font-medium">Started</th>
						<th class="py-2 pr-4 font-medium">Finished</th>
						<th class="py-2 pr-4 font-medium">Duration</th>
						<th class="py-2 pr-4 font-medium">Video</th>
						<th class="py-2 font-medium"><span class="sr-only">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each jobs as job (job.id)}
						<tr class="border-b border-gray-800/50 text-gray-200">
							<td class="py-2 pr-4">{job.gcode_name || 'Untitled print'}</td>
							<td class="py-2 pr-4">
								{#if job.status === 'printing'}
									<span class="rounded-full bg-blue-900 px-2 py-0.5 text-xs text-blue-300">Printing</span>
								{:else if job.status === 'finished'}
									<span class="rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300">Finished</span>
								{:else}
									<span class="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300">Cancelled</span>
								{/if}
							</td>
							<td class="py-2 pr-4">{formatDateTime(job.started_at)}</td>
							<td class="py-2 pr-4">{formatFinishedAt(job.started_at, job.finished_at)}</td>
							<td class="py-2 pr-4">{duration(job)}</td>
							<td class="py-2 pr-4">
								{#if job.timelapse_id}
									<button onclick={() => play(job)} class="text-blue-400 hover:text-blue-300">Play</button>
								{:else}
									<span class="text-gray-500">—</span>
								{/if}
							</td>
							<td class="py-2 text-right">
								{#if job.status === 'printing'}
									<span class="text-xs text-gray-600" title="Finish or cancel the print first">—</span>
								{:else}
									<button
										onclick={() => { deleteTarget = job; deleteWithTimelapse = false; }}
										aria-label="Delete print {job.gcode_name || 'Untitled print'}"
										class="text-gray-500 transition-colors hover:text-red-400"
									>
										<svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
										</svg>
									</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

{#if selected}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
		onclick={(e) => { if (e.target === e.currentTarget) selected = null; }}
	>
		<div class="mx-4 w-full max-w-3xl rounded-xl bg-gray-900 shadow-xl">
			<div class="flex items-center justify-between border-b border-gray-800 p-4">
				<h2 class="text-lg font-semibold text-gray-100">Print timelapse</h2>
				<button onclick={() => { selected = null; }} aria-label="Close" class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="p-4"><TimelapsePlayer timelapse={selected} /></div>
		</div>
	</div>
{/if}

{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
		onclick={(e) => { if (e.target === e.currentTarget) deleteTarget = null; }}
	>
		<div class="w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl">
			<h3 class="mb-2 text-lg font-semibold text-gray-100">Delete print?</h3>
			<p class="mb-4 text-sm text-gray-400">{deleteTarget.gcode_name || 'Untitled print'}</p>
			{#if deleteTarget.timelapse_id}
				<!-- Defaults to keeping the video: the history row is cheap to lose,
				     the render is not. -->
				<label class="mb-4 flex items-center gap-2 text-sm text-gray-300">
					<input type="checkbox" bind:checked={deleteWithTimelapse} class="rounded border-gray-600 bg-gray-800" />
					Also delete the timelapse video
				</label>
			{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => { deleteTarget = null; }} class="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-gray-600">
					Cancel
				</button>
				<button onclick={confirmDelete} disabled={deleting} class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50">
					{deleting ? 'Deleting…' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}
