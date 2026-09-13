<script lang="ts">
	import { api } from '$lib/api';
	import { formatDateTime, formatCronTime } from '$lib/utils';
	import type { Profile, TimelapseSchedule } from '$lib/types';

	interface Props {
		/** This camera's capture plans. */
		profiles: Profile[];
		/** Bump to refetch after something changes it. */
		refreshKey?: number;
		onadd: () => void;
	}

	let { profiles, refreshKey = 0, onadd }: Props = $props();

	let schedules = $state<TimelapseSchedule[]>([]);
	let loaded = $state(false);

	// One call for every schedule, filtered here — a per-plan fan-out is the
	// pattern that was deliberately removed elsewhere.
	$effect(() => {
		refreshKey;
		const ids = new Set(profiles.map((p) => p.id));
		api.getTimelapseSchedules()
			.then((all) => {
				schedules = all.filter((s) => ids.has(s.profile_id));
				loaded = true;
			})
			.catch(() => {
				schedules = [];
				loaded = true;
			});
	});

	const DESCRIPTIONS: Record<string, () => string> = {
		daily: () => `Every day at ${formatCronTime(0, 5)}`,
		weekly: () => `Sunday at ${formatCronTime(0, 30)}`,
		monthly: () => `1st of month at ${formatCronTime(1, 0)}`,
		yearly: () => `Jan 1 at ${formatCronTime(2, 0)}`
	};

	function describe(s: TimelapseSchedule): string {
		return s.preset && DESCRIPTIONS[s.preset] ? DESCRIPTIONS[s.preset]() : s.cron_expression;
	}

	function planName(profileId: number): string {
		return profiles.find((p) => p.id === profileId)?.name ?? `Plan #${profileId}`;
	}
</script>

<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
	<div class="mb-4 flex items-center justify-between">
		<h2 class="text-lg font-semibold text-gray-100">Render schedules</h2>
		<button
			onclick={onadd}
			disabled={profiles.length === 0}
			title={profiles.length === 0 ? 'Add a capture plan first' : undefined}
			class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
		>
			Add render schedule
		</button>
	</div>

	{#if !loaded}
		<p class="text-sm text-gray-500">Loading…</p>
	{:else if schedules.length === 0}
		<p class="text-sm text-gray-500">
			{#if profiles.length === 0}
				Nothing to render yet — this camera has no capture plan.
			{:else}
				No schedules. Frames are captured and kept, but no timelapse is produced
				automatically.
			{/if}
		</p>
	{:else}
		<div class="space-y-2">
			{#each schedules as schedule (schedule.id)}
				<div class="flex items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-800/50 p-3 {schedule.enabled ? '' : 'opacity-50'}">
					<div class="min-w-0">
						<div class="flex flex-wrap items-center gap-2">
							<span class="text-sm font-medium text-gray-200">{schedule.name || 'Schedule'}</span>
							<span class="rounded bg-teal-900/50 px-1.5 py-0.5 text-xs text-teal-300">{planName(schedule.profile_id)}</span>
							{#if !schedule.enabled}
								<span class="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">Disabled</span>
							{/if}
						</div>
						<div class="mt-1 flex flex-wrap items-center gap-3 text-xs text-gray-500">
							<span>{describe(schedule)}</span>
							<span>{schedule.fps}fps · {schedule.format.toUpperCase()}</span>
							{#if schedule.next_run}
								<span>Next: {formatDateTime(schedule.next_run)}</span>
							{/if}
						</div>
					</div>
				</div>
			{/each}
		</div>

		<!-- Deliberately read-only: this answers "does it render?" without
		     becoming a second copy of the schedules library. -->
		<a href="/timelapses" class="mt-3 inline-block text-xs text-blue-400 hover:text-blue-300">
			Manage schedules in Timelapses →
		</a>
	{/if}
</div>
