<script lang="ts">
	import { api } from '$lib/api';
	import type { StatsSummary, StorageTrendPoint, CaptureActivityPoint, ProfileStoragePoint, Profile } from '$lib/types';
	import LineChart from '$lib/components/LineChart.svelte';
	import type uPlot from 'uplot';

	let summary = $state<StatsSummary | null>(null);
	let trendData = $state<StorageTrendPoint[]>([]);
	let activityData = $state<CaptureActivityPoint[]>([]);
	let storageData = $state<ProfileStoragePoint[]>([]);
	let profiles = $state<Profile[]>([]);

	let trendDays = $state(90);
	let activityDays = $state(30);
	let storageDays = $state(30);
	let selectedProfileId = $state<number | undefined>(undefined);

	let loading = $state(true);

	function formatBytes(b: number): string {
		if (b < 1024) return `${b} B`;
		if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
		if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
		return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`;
	}

	function formatDate(v: number): string {
		const d = new Date(v * 1000);
		return `${d.getMonth() + 1}/${d.getDate()}`;
	}

	const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

	function profileName(id: number): string {
		const p = profiles.find((p) => p.id === id);
		return p ? p.name : `Profile ${id}`;
	}

	async function loadProfiles() {
		try {
			const streams = await api.getStreams();
			const all: Profile[] = [];
			for (const s of streams) {
				const ps = await api.getStreamProfiles(s.id);
				all.push(...ps);
			}
			profiles = all;
		} catch {}
	}

	async function loadSummary() {
		try {
			summary = await api.getStatsSummary();
		} catch {}
	}

	async function loadTrend() {
		try {
			trendData = await api.getStorageTrend(trendDays);
		} catch {}
	}

	async function loadActivity() {
		try {
			activityData = await api.getCaptureActivity(activityDays, selectedProfileId);
		} catch {}
	}

	async function loadStorage() {
		try {
			storageData = await api.getProfileStorage(storageDays, selectedProfileId);
		} catch {}
	}

	$effect(() => {
		Promise.all([loadProfiles(), loadSummary()]).then(() => { loading = false; });
	});

	$effect(() => { trendDays; loadTrend(); });
	$effect(() => { activityDays; selectedProfileId; loadActivity(); });
	$effect(() => { storageDays; selectedProfileId; loadStorage(); });

	// Chart data derivations
	let trendChartData = $derived.by((): uPlot.AlignedData => {
		if (!trendData.length) return [[], []];
		const xs = trendData.map((p) => new Date(p.date).getTime() / 1000);
		const ys = trendData.map((p) => p.cumulative_bytes / (1024 * 1024));
		return [xs, ys];
	});

	let trendSeries = $derived.by((): uPlot.Series[] => [
		{
			label: 'Total (MB)',
			stroke: '#3b82f6',
			fill: 'rgba(59,130,246,0.1)',
			width: 2
		}
	]);

	let activityChartData = $derived.by((): uPlot.AlignedData => {
		if (!activityData.length) return [[], []];
		const profileIds = [...new Set(activityData.map((p) => p.profile_id))];
		const dateMap = new Map<string, Map<number, number>>();
		for (const p of activityData) {
			if (!dateMap.has(p.date)) dateMap.set(p.date, new Map());
			dateMap.get(p.date)!.set(p.profile_id, p.count);
		}
		const dates = [...dateMap.keys()].sort();
		const xs = dates.map((d) => new Date(d).getTime() / 1000);
		const series: (number | null)[][] = profileIds.map((pid) =>
			dates.map((d) => dateMap.get(d)?.get(pid) ?? null)
		);
		return [xs, ...series];
	});

	let activitySeries = $derived.by((): uPlot.Series[] => {
		const profileIds = [...new Set(activityData.map((p) => p.profile_id))];
		return profileIds.map((pid, i) => ({
			label: profileName(pid),
			stroke: COLORS[i % COLORS.length],
			width: 2
		}));
	});

	let storageChartData = $derived.by((): uPlot.AlignedData => {
		if (!storageData.length) return [[], []];
		const profileIds = [...new Set(storageData.map((p) => p.profile_id))];
		const dateMap = new Map<string, Map<number, number>>();
		for (const p of storageData) {
			if (!dateMap.has(p.date)) dateMap.set(p.date, new Map());
			dateMap.get(p.date)!.set(p.profile_id, p.bytes / (1024 * 1024));
		}
		const dates = [...dateMap.keys()].sort();
		const xs = dates.map((d) => new Date(d).getTime() / 1000);
		const series: (number | null)[][] = profileIds.map((pid) =>
			dates.map((d) => dateMap.get(d)?.get(pid) ?? null)
		);
		return [xs, ...series];
	});

	let storageSeries = $derived.by((): uPlot.Series[] => {
		const profileIds = [...new Set(storageData.map((p) => p.profile_id))];
		return profileIds.map((pid, i) => ({
			label: profileName(pid),
			stroke: COLORS[i % COLORS.length],
			width: 2
		}));
	});

	// Disk-full projection from last 14 days of trend data
	let projectionDays = $derived.by((): number | null => {
		if (!trendData.length) return null;
		const recent = trendData.slice(-14);
		if (recent.length < 2) return null;
		const totalAdded = recent.reduce((s, p) => s + p.bytes_added, 0);
		const dailyRate = totalAdded / recent.length;
		if (dailyRate <= 0) return null;
		if (!summary) return null;
		// Use summary.days_until_full if available, otherwise estimate
		return summary.days_until_full;
	});
</script>

<div class="space-y-6">
	<h1 class="text-3xl font-bold text-white">Statistics</h1>

	{#if loading}
		<div class="flex items-center gap-2 text-gray-400">
			<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
			</svg>
			Loading statistics...
		</div>
	{:else}
		<!-- Summary Cards -->
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<p class="text-sm text-gray-400">Total Captures</p>
				<p class="mt-1 text-2xl font-bold text-white">{summary?.total_captures.toLocaleString() ?? 0}</p>
			</div>
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<p class="text-sm text-gray-400">Avg Captures/Day</p>
				<p class="mt-1 text-2xl font-bold text-white">{summary?.avg_captures_per_day ?? 0}</p>
			</div>
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<p class="text-sm text-gray-400">Avg Storage/Day</p>
				<p class="mt-1 text-2xl font-bold text-white">{formatBytes(summary?.avg_bytes_per_day ?? 0)}</p>
			</div>
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<p class="text-sm text-gray-400">Days Until Full</p>
				{#if summary?.days_until_full == null}
					<p class="mt-1 text-2xl font-bold text-gray-500">&mdash;</p>
				{:else}
					<p class="mt-1 text-2xl font-bold {summary.days_until_full < 30 ? 'text-red-400' : summary.days_until_full < 90 ? 'text-yellow-400' : 'text-green-400'}">
						{Math.round(summary.days_until_full)}
					</p>
				{/if}
			</div>
		</div>

		<!-- Storage Trend -->
		<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Storage Trend</h2>
				<select
					bind:value={trendDays}
					class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-300"
				>
					<option value={30}>30 days</option>
					<option value={90}>90 days</option>
					<option value={180}>180 days</option>
					<option value={365}>365 days</option>
				</select>
			</div>
			{#if projectionDays != null}
				<div class="mb-3 rounded border px-3 py-2 text-sm {projectionDays < 30 ? 'border-red-800 bg-red-950 text-red-300' : projectionDays < 90 ? 'border-yellow-800 bg-yellow-950 text-yellow-300' : 'border-blue-800 bg-blue-950 text-blue-300'}">
					At current rate, disk will be full in ~{Math.round(projectionDays)} days
				</div>
			{/if}
			{#if trendData.length}
				<LineChart data={trendChartData} series={trendSeries} height={280} xFormatter={formatDate} />
			{:else}
				<p class="py-12 text-center text-gray-500">No data yet</p>
			{/if}
		</div>

		<!-- Filters for per-profile charts -->
		<div class="flex flex-wrap items-center gap-3">
			<select
				bind:value={selectedProfileId}
				class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-300"
			>
				<option value={undefined}>All Profiles</option>
				{#each profiles as p}
					<option value={p.id}>{p.name}</option>
				{/each}
			</select>
		</div>

		<!-- Per-Profile Charts -->
		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg font-semibold text-white">Capture Activity</h2>
					<select
						bind:value={activityDays}
						class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-300"
					>
						<option value={7}>7 days</option>
						<option value={30}>30 days</option>
						<option value={90}>90 days</option>
					</select>
				</div>
				{#if activityData.length}
					<LineChart data={activityChartData} series={activitySeries} height={250} xFormatter={formatDate} />
				{:else}
					<p class="py-12 text-center text-gray-500">No data yet</p>
				{/if}
			</div>

			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg font-semibold text-white">Storage by Profile</h2>
					<select
						bind:value={storageDays}
						class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-300"
					>
						<option value={7}>7 days</option>
						<option value={30}>30 days</option>
						<option value={90}>90 days</option>
					</select>
				</div>
				{#if storageData.length}
					<LineChart data={storageChartData} series={storageSeries} height={250} xFormatter={formatDate} />
				{:else}
					<p class="py-12 text-center text-gray-500">No data yet</p>
				{/if}
			</div>
		</div>
	{/if}
</div>
