<script lang="ts">
	import { api } from '$lib/api';
	import type { StatsSummary, StorageTrendPoint, CaptureActivityPoint, ProfileStoragePoint, Profile, Stream, StorageStats, TimelapseSummary } from '$lib/types';
	import { formatBytes, formatDuration } from '$lib/utils';
	import LineChart from '$lib/components/LineChart.svelte';
	import type uPlot from 'uplot';

	let summary = $state<StatsSummary | null>(null);
	let trendData = $state<StorageTrendPoint[]>([]);
	let activityData = $state<CaptureActivityPoint[]>([]);
	let storageData = $state<ProfileStoragePoint[]>([]);
	let profiles = $state<Profile[]>([]);
	let streams = $state<Stream[]>([]);
	let storageStats = $state<StorageStats | null>(null);
	let timelapseSummary = $state<TimelapseSummary | null>(null);

	let trendDays = $state(90);
	let activityDays = $state(30);
	let storageDays = $state(30);
	let selectedProfileId = $state<number | undefined>(undefined);

	let loading = $state(true);

	function formatChartDate(v: number): string {
		const d = new Date(v * 1000);
		return `${d.getMonth() + 1}/${d.getDate()}`;
	}

	const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

	function profileName(id: number): string {
		const p = profiles.find((p) => p.id === id);
		if (!p) return `Profile ${id}`;
		const s = streams.find((s) => s.id === p.stream_id);
		return s ? `${s.name} / ${p.name}` : p.name;
	}

	async function loadProfiles() {
		try {
			const fetchedStreams = await api.getStreams();
			streams = fetchedStreams;
			const all: Profile[] = [];
			for (const s of fetchedStreams) {
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

	async function loadStorageStats() {
		try {
			storageStats = await api.getStorage();
		} catch {}
	}

	async function loadTimelapseSummary() {
		try {
			timelapseSummary = await api.getTimelapseSummary();
		} catch {}
	}

	$effect(() => {
		Promise.all([loadProfiles(), loadSummary(), loadStorageStats(), loadTimelapseSummary()]).then(() => { loading = false; });
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

<svelte:head><title>Statistics - Lapsora</title></svelte:head>

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

		<!-- Disk Usage Breakdown -->
		{#if storageStats}
			{@const capturesBytes = storageStats.captures_size_bytes}
			{@const timelapsesBytes = storageStats.timelapses_size_bytes}
			{@const otherBytes = Math.max(0, storageStats.disk_total_bytes - storageStats.disk_free_bytes - storageStats.total_size_bytes)}
			{@const freeBytes = storageStats.disk_free_bytes}
			{@const totalDisk = storageStats.disk_total_bytes || 1}
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<h2 class="mb-3 text-lg font-semibold text-white">Disk Usage Breakdown</h2>
				<div class="mb-4 flex h-6 w-full overflow-hidden rounded-full bg-gray-800">
					{#if capturesBytes > 0}
						<div class="bg-blue-500 transition-all" style="width: {(capturesBytes / totalDisk) * 100}%" title="Captures: {formatBytes(capturesBytes)}"></div>
					{/if}
					{#if timelapsesBytes > 0}
						<div class="bg-purple-500 transition-all" style="width: {(timelapsesBytes / totalDisk) * 100}%" title="Timelapses: {formatBytes(timelapsesBytes)}"></div>
					{/if}
					{#if otherBytes > 0}
						<div class="bg-yellow-500 transition-all" style="width: {(otherBytes / totalDisk) * 100}%" title="Other: {formatBytes(otherBytes)}"></div>
					{/if}
					{#if freeBytes > 0}
						<div class="bg-gray-600 transition-all" style="width: {(freeBytes / totalDisk) * 100}%" title="Free: {formatBytes(freeBytes)}"></div>
					{/if}
				</div>
				<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<div class="flex items-center gap-2">
							<div class="h-3 w-3 rounded-full bg-blue-500"></div>
							<p class="text-sm text-gray-400">Captures</p>
						</div>
						<p class="mt-1 text-lg font-bold text-white">{formatBytes(capturesBytes)}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<div class="flex items-center gap-2">
							<div class="h-3 w-3 rounded-full bg-purple-500"></div>
							<p class="text-sm text-gray-400">Timelapses</p>
						</div>
						<p class="mt-1 text-lg font-bold text-white">{formatBytes(timelapsesBytes)}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<div class="flex items-center gap-2">
							<div class="h-3 w-3 rounded-full bg-yellow-500"></div>
							<p class="text-sm text-gray-400">Other</p>
						</div>
						<p class="mt-1 text-lg font-bold text-white">{formatBytes(otherBytes)}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<div class="flex items-center gap-2">
							<div class="h-3 w-3 rounded-full bg-gray-600"></div>
							<p class="text-sm text-gray-400">Free Space</p>
						</div>
						<p class="mt-1 text-lg font-bold text-white">{formatBytes(freeBytes)}</p>
					</div>
				</div>
			</div>
		{/if}

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
				<LineChart data={trendChartData} series={trendSeries} height={280} xFormatter={formatChartDate} />
			{:else}
				<p class="py-12 text-center text-gray-500">No data yet</p>
			{/if}
		</div>

		<!-- Filters for per-profile charts -->
		<div class="flex flex-wrap items-center gap-3">
			<select
				onchange={(e) => {
					const val = (e.target as HTMLSelectElement).value;
					selectedProfileId = val ? Number(val) : undefined;
				}}
				class="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-300"
			>
				<option value="">All Profiles</option>
				{#each profiles as p}
					<option value={p.id} selected={selectedProfileId === p.id}>{profileName(p.id)}</option>
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
					<LineChart data={activityChartData} series={activitySeries} height={250} xFormatter={formatChartDate} />
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
					<LineChart data={storageChartData} series={storageSeries} height={250} xFormatter={formatChartDate} />
				{:else}
					<p class="py-12 text-center text-gray-500">No data yet</p>
				{/if}
			</div>
		</div>

		<!-- Timelapse Stats -->
		{#if timelapseSummary}
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<h2 class="mb-3 text-lg font-semibold text-white">Timelapse Stats</h2>
				<div class="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<p class="text-sm text-gray-400">Total Count</p>
						<p class="mt-1 text-lg font-bold text-white">{timelapseSummary.total_count.toLocaleString()}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<p class="text-sm text-gray-400">Total Size</p>
						<p class="mt-1 text-lg font-bold text-white">{formatBytes(timelapseSummary.total_size_bytes)}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<p class="text-sm text-gray-400">Total Frames</p>
						<p class="mt-1 text-lg font-bold text-white">{timelapseSummary.total_frames.toLocaleString()}</p>
					</div>
					<div class="rounded-lg border border-gray-800 bg-gray-950 p-3">
						<p class="text-sm text-gray-400">Total Duration</p>
						<p class="mt-1 text-lg font-bold text-white">{formatDuration(timelapseSummary.total_duration_seconds)}</p>
					</div>
				</div>
				{#if timelapseSummary.by_format.length}
					<div class="overflow-x-auto">
						<table class="w-full text-left text-sm">
							<thead>
								<tr class="border-b border-gray-800 text-gray-400">
									<th class="pb-2 pr-4">Format</th>
									<th class="pb-2 pr-4">Count</th>
									<th class="pb-2 pr-4">Size</th>
									<th class="pb-2">Duration</th>
								</tr>
							</thead>
							<tbody>
								{#each timelapseSummary.by_format as fmt}
									<tr class="border-b border-gray-800/50">
										<td class="py-2 pr-4"><span class="rounded bg-purple-900 px-2 py-0.5 text-xs font-medium text-purple-300">{fmt.format.toUpperCase()}</span></td>
										<td class="py-2 pr-4 text-white">{fmt.count.toLocaleString()}</td>
										<td class="py-2 pr-4 text-white">{formatBytes(fmt.total_size_bytes)}</td>
										<td class="py-2 text-white">{formatDuration(fmt.total_duration_seconds)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="py-4 text-center text-gray-500">No timelapses yet</p>
				{/if}
			</div>
		{/if}

		<!-- Stream Health -->
		{#if streams.length}
			{@const healthy = streams.filter(s => s.health_status === 'healthy').length}
			{@const unhealthy = streams.filter(s => s.health_status === 'unhealthy').length}
			{@const unknown = streams.filter(s => s.health_status !== 'healthy' && s.health_status !== 'unhealthy').length}
			<div class="rounded-lg border border-gray-800 bg-gray-900 p-4">
				<h2 class="mb-3 text-lg font-semibold text-white">Stream Health</h2>
				<div class="mb-4 flex items-center gap-4 text-sm">
					<span class="flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-full bg-green-500"></span> {healthy} healthy</span>
					<span class="flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-full bg-red-500"></span> {unhealthy} unhealthy</span>
					<span class="flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-full bg-gray-500"></span> {unknown} unknown</span>
				</div>
				<div class="overflow-x-auto">
					<table class="w-full text-left text-sm">
						<thead>
							<tr class="border-b border-gray-800 text-gray-400">
								<th class="pb-2 pr-4">Stream</th>
								<th class="pb-2 pr-4">Status</th>
								<th class="pb-2 pr-4">Failures</th>
								<th class="pb-2 pr-4">Last Checked</th>
								<th class="pb-2">Enabled</th>
							</tr>
						</thead>
						<tbody>
							{#each streams as stream}
								<tr class="border-b border-gray-800/50">
									<td class="py-2 pr-4 text-white">{stream.name}</td>
									<td class="py-2 pr-4">
										<span class="flex items-center gap-1.5">
											<span class="inline-block h-2.5 w-2.5 rounded-full {stream.health_status === 'healthy' ? 'bg-green-500' : stream.health_status === 'unhealthy' ? 'bg-red-500' : 'bg-gray-500'}"></span>
											<span class="{stream.health_status === 'healthy' ? 'text-green-400' : stream.health_status === 'unhealthy' ? 'text-red-400' : 'text-gray-400'}">{stream.health_status}</span>
										</span>
									</td>
									<td class="py-2 pr-4 text-white">{stream.consecutive_failures}</td>
									<td class="py-2 pr-4 text-gray-400">{stream.last_checked_at ? new Date(stream.last_checked_at).toLocaleString() : '—'}</td>
									<td class="py-2">{#if stream.enabled}<span class="text-green-400">Yes</span>{:else}<span class="text-gray-500">No</span>{/if}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	{/if}
</div>
