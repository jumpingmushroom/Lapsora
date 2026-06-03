<script lang="ts">
	import type { Stream } from '$lib/types';
	import { api } from '$lib/api';
	import { timeAgo, healthDotClass } from '$lib/utils';

	interface Props {
		stream: Stream;
		profileCount: number;
	}

	let { stream, profileCount }: Props = $props();

	let previewKey = $state(0);

	$effect(() => {
		const interval = setInterval(() => {
			previewKey++;
		}, 30000);
		return () => clearInterval(interval);
	});

	let previewSrc = $derived(`${api.getStreamPreviewUrl(stream.id)}?t=${previewKey}`);

	let dotClass = $derived(healthDotClass(stream.health_status));
</script>

<a
	href="/streams/{stream.id}"
	class="block rounded-lg bg-gray-800 p-4 transition-colors hover:bg-gray-700"
>
	<div class="mb-3 aspect-video w-full overflow-hidden rounded-md bg-gray-900">
		<img
			src={previewSrc}
			alt="{stream.name} preview"
			class="h-full w-full object-cover"
			onerror={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
		/>
	</div>

	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<span class="h-2.5 w-2.5 rounded-full {dotClass}" title="{stream.health_status}"></span>
			<h3 class="text-lg font-semibold text-gray-100">{stream.name}</h3>
		</div>
		<span
			class="rounded-full px-2 py-0.5 text-xs font-medium {stream.enabled
				? 'bg-green-900 text-green-300'
				: 'bg-red-900 text-red-300'}"
		>
			{stream.enabled ? 'Enabled' : 'Disabled'}
		</span>
	</div>

	<div class="mt-2 flex items-center justify-between text-sm text-gray-400">
		<span>{profileCount} profile{profileCount !== 1 ? 's' : ''}</span>
		<span>Checked {timeAgo(stream.last_checked_at)}</span>
	</div>
</a>
