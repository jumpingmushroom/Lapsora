<script lang="ts">
	import type { Timelapse } from '$lib/types';
	import { api } from '$lib/api';

	interface Props {
		timelapse: Timelapse;
	}

	let { timelapse }: Props = $props();

	let videoUrl = $derived(api.getTimelapseVideoUrl(timelapse.id));

	function formatBytes(bytes: number | null): string {
		if (bytes === null || bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null) return '--';
		const m = Math.floor(seconds / 60);
		const s = Math.round(seconds % 60);
		return m > 0 ? `${m}m ${s}s` : `${s}s`;
	}
</script>

<div class="rounded-lg bg-gray-800 p-4">
	<div class="mb-4 aspect-video w-full overflow-hidden rounded-md bg-black">
		<!-- svelte-ignore a11y_media_has_caption -->
		<video controls class="h-full w-full" src={videoUrl}>
			Your browser does not support the video element.
		</video>
	</div>

	<div class="mb-4 grid grid-cols-2 gap-2 text-sm text-gray-400 sm:grid-cols-3">
		<div>
			<span class="text-gray-500">Format:</span>
			<span class="ml-1 text-gray-300">{timelapse.format}</span>
		</div>
		<div>
			<span class="text-gray-500">FPS:</span>
			<span class="ml-1 text-gray-300">{timelapse.fps}</span>
		</div>
		<div>
			<span class="text-gray-500">Frames:</span>
			<span class="ml-1 text-gray-300">{timelapse.frame_count ?? '--'}</span>
		</div>
		<div>
			<span class="text-gray-500">Duration:</span>
			<span class="ml-1 text-gray-300">{formatDuration(timelapse.duration_seconds)}</span>
		</div>
		<div>
			<span class="text-gray-500">Size:</span>
			<span class="ml-1 text-gray-300">{formatBytes(timelapse.file_size)}</span>
		</div>
	</div>

	<a
		href={videoUrl}
		download
		class="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
	>
		Download
	</a>
</div>
