<script lang="ts">
	import { formatCronTime } from '$lib/utils';

	interface Props {
		/** 'daily' | 'weekly' | 'none' */
		value: string;
		/** Leading sentence, so the step can be framed by whoever opens it. */
		intro?: string;
	}

	let {
		value = $bindable(),
		intro = 'Rendering turns the captured frames into a video. You can change or add schedules later.'
	}: Props = $props();

	// Cron values must match the backend's PRESET_CRONS, or a schedule created
	// here would describe itself differently from every other one. The times are
	// rendered through formatCronTime for the same reason.
	const CHOICES = [
		{ value: 'daily', title: 'Every day', detail: () => `at ${formatCronTime(0, 5)}` },
		{ value: 'weekly', title: 'Every week', detail: () => `Sunday at ${formatCronTime(0, 30)}` },
		{ value: 'none', title: "I'll set this up later", detail: () => 'Frames are still captured and kept' }
	];
</script>

<p class="text-sm text-gray-400">{intro}</p>

<div class="space-y-2">
	{#each CHOICES as choice}
		<button
			type="button"
			onclick={() => { value = choice.value; }}
			class="flex w-full flex-col items-start rounded-lg border p-3 text-left transition-colors {
				value === choice.value
					? 'border-blue-500 bg-blue-950/40'
					: 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
			}"
		>
			<span class="text-sm font-medium text-gray-100">{choice.title}</span>
			<span class="mt-0.5 text-xs text-gray-500">{choice.detail()}</span>
		</button>
	{/each}
</div>
