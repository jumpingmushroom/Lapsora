<script lang="ts">
	import { api } from '$lib/api';

	interface Props {
		profileId: number;
		open: boolean;
		onclose: () => void;
	}

	let { profileId, open, onclose }: Props = $props();

	let period_start = $state('');
	let period_end = $state('');
	let fps = $state(24);
	let format = $state('mp4');
	let timestamp_overlay = $state(false);
	let loading = $state(false);
	let error = $state('');

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		loading = true;
		error = '';
		try {
			await api.generateTimelapse(profileId, {
				period_start: period_start || undefined,
				period_end: period_end || undefined,
				fps,
				format,
				timestamp_overlay
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
					<label for="gen-start" class="mb-1 block text-sm font-medium text-gray-300">Start</label>
					<input
						id="gen-start"
						type="datetime-local"
						bind:value={period_start}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

				<div>
					<label for="gen-end" class="mb-1 block text-sm font-medium text-gray-300">End</label>
					<input
						id="gen-end"
						type="datetime-local"
						bind:value={period_end}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

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

				<div class="flex items-center gap-3">
					<input
						id="gen-overlay"
						type="checkbox"
						bind:checked={timestamp_overlay}
						class="h-4 w-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
					/>
					<label for="gen-overlay" class="text-sm font-medium text-gray-300">Timestamp overlay</label>
				</div>

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
