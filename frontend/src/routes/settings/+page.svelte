<script lang="ts">
	import { api } from '$lib/api';
	import type { NotificationURL, NotificationEventsConfig, HealthConfig, LocationConfig, CaptureGapConfig, Go2rtcConfig } from '$lib/types';
	import CleanupScheduleManager from '$lib/components/CleanupScheduleManager.svelte';

	let urls = $state<NotificationURL[]>([]);
	let events = $state<NotificationEventsConfig>({
		capture_failure: true,
		stream_unhealthy: true,
		stream_recovered: true,
		timelapse_complete: true,
		timelapse_failure: true,
		retention_summary: false,
		low_disk_space: true
	});
	let healthConfig = $state<HealthConfig>({
		check_interval_seconds: 300,
		failure_threshold: 3,
		low_disk_threshold_percent: 10
	});
	let locationConfig = $state<LocationConfig>({
		latitude: 0.0,
		longitude: 0.0
	});

	let captureGapConfig = $state<CaptureGapConfig>({ enabled: true });
	let savingCaptureGap = $state(false);

	let go2rtcConfig = $state<Go2rtcConfig>({ url: '' });
	let savingGo2rtc = $state(false);
	let testingGo2rtc = $state(false);
	let go2rtcTestResult = $state<string | null>(null);

	let loading = $state(true);
	let newLabel = $state('');
	let newUrl = $state('');
	let testingId = $state<number | null>(null);
	let savingEvents = $state(false);
	let savingHealth = $state(false);
	let savingLocation = $state(false);

	$effect(() => {
		Promise.all([api.getNotificationSettings(), api.getHealthConfig(), api.getLocationConfig(), api.getCaptureGapConfig(), api.getGo2rtcConfig()])
			.then(([notifSettings, hc, loc, gapCfg, g2rCfg]) => {
				urls = notifSettings.urls;
				events = notifSettings.events;
				healthConfig = hc;
				locationConfig = loc;
				captureGapConfig = gapCfg;
				go2rtcConfig = g2rCfg;
			})
			.finally(() => {
				loading = false;
			});
	});

	async function addUrl() {
		if (!newLabel.trim() || !newUrl.trim()) return;
		const nu = await api.addNotificationURL({ label: newLabel.trim(), url: newUrl.trim() });
		urls = [...urls, nu];
		newLabel = '';
		newUrl = '';
	}

	async function removeUrl(id: number) {
		await api.deleteNotificationURL(id);
		urls = urls.filter((u) => u.id !== id);
	}

	async function toggleUrl(nu: NotificationURL) {
		const updated = await api.updateNotificationURL(nu.id, { enabled: !nu.enabled });
		urls = urls.map((u) => (u.id === updated.id ? updated : u));
	}

	async function testUrl(id: number) {
		testingId = id;
		try {
			const result = await api.testNotificationURL(id);
			alert(result.success ? 'Test notification sent!' : 'Test notification failed.');
		} catch {
			alert('Failed to send test notification.');
		}
		testingId = null;
	}

	async function saveEvents() {
		savingEvents = true;
		await api.updateNotificationEvents(events);
		savingEvents = false;
	}

	async function saveHealth() {
		savingHealth = true;
		await api.updateHealthConfig(healthConfig);
		savingHealth = false;
	}

	async function saveLocation() {
		savingLocation = true;
		await api.updateLocationConfig(locationConfig);
		savingLocation = false;
	}

	async function saveCaptureGap() {
		savingCaptureGap = true;
		await api.updateCaptureGapConfig(captureGapConfig);
		savingCaptureGap = false;
	}

	async function saveGo2rtc() {
		savingGo2rtc = true;
		go2rtcTestResult = null;
		await api.updateGo2rtcConfig(go2rtcConfig);
		savingGo2rtc = false;
	}

	async function testGo2rtc() {
		testingGo2rtc = true;
		go2rtcTestResult = null;
		try {
			const result = await api.testGo2rtcServer(go2rtcConfig);
			go2rtcTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
		} catch (err) {
			go2rtcTestResult = err instanceof Error ? err.message : 'Test failed';
		}
		testingGo2rtc = false;
	}

	const eventLabels: Record<string, string> = {
		capture_failure: 'Capture failure',
		stream_unhealthy: 'Stream unhealthy',
		stream_recovered: 'Stream recovered',
		timelapse_complete: 'Timelapse complete',
		timelapse_failure: 'Timelapse failure',
		retention_summary: 'Retention summary',
		low_disk_space: 'Low disk space',
		capture_gap: 'Capture gap'
	};
</script>

<div class="space-y-8">
	<h1 class="text-3xl font-bold text-white">Settings</h1>

	{#if loading}
		<p class="text-gray-400">Loading settings...</p>
	{:else}
		<!-- Notification URLs -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Notification URLs</h2>
			<p class="mb-4 text-sm text-gray-400">
				Add Apprise-compatible URLs to receive alerts via Discord, Telegram, email, ntfy, and 100+ services.
			</p>

			{#if urls.length > 0}
				<div class="mb-4 space-y-2">
					{#each urls as nu}
						<div class="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 p-3">
							<div class="flex items-center gap-3">
								<button
									onclick={() => toggleUrl(nu)}
									class="rounded px-2 py-1 text-xs font-medium transition-colors {nu.enabled ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}"
								>
									{nu.enabled ? 'On' : 'Off'}
								</button>
								<span class="text-sm text-gray-200">{nu.label}</span>
							</div>
							<div class="flex items-center gap-2">
								<button
									onclick={() => testUrl(nu.id)}
									disabled={testingId === nu.id}
									class="rounded bg-blue-900 px-3 py-1 text-xs text-blue-300 transition-colors hover:bg-blue-800 disabled:opacity-50"
								>
									{testingId === nu.id ? 'Testing...' : 'Test'}
								</button>
								<button
									onclick={() => removeUrl(nu.id)}
									class="rounded bg-red-900 px-3 py-1 text-xs text-red-300 transition-colors hover:bg-red-800"
								>
									Delete
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<div class="flex gap-2">
				<input
					bind:value={newLabel}
					placeholder="Label (e.g. Discord)"
					class="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
				<input
					bind:value={newUrl}
					placeholder="Apprise URL (e.g. discord://...)"
					class="flex-[2] rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
				<button
					onclick={addUrl}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
				>
					Add
				</button>
			</div>
		</section>

		<!-- Event Toggles -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Notification Events</h2>
			<p class="mb-4 text-sm text-gray-400">
				Choose which events trigger external notifications (Apprise). All events always appear in the in-app notification panel.
			</p>

			<div class="mb-4 grid grid-cols-2 gap-3">
				{#each Object.entries(eventLabels) as [key, label]}
					<label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-800/50 p-3">
						<input
							type="checkbox"
							bind:checked={events[key as keyof NotificationEventsConfig]}
							class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
						/>
						<span class="text-sm text-gray-200">{label}</span>
					</label>
				{/each}
			</div>

			<button
				onclick={saveEvents}
				disabled={savingEvents}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingEvents ? 'Saving...' : 'Save Event Settings'}
			</button>
		</section>

		<!-- Health Monitoring -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Health Monitoring</h2>
			<p class="mb-4 text-sm text-gray-400">
				Configure how often streams are checked and when they're marked as unhealthy.
			</p>

			<div class="mb-4 grid grid-cols-3 gap-4">
				<div>
					<label for="check-interval" class="mb-1 block text-sm text-gray-400">Check interval (seconds)</label>
					<input
						id="check-interval"
						type="number"
						min="30"
						bind:value={healthConfig.check_interval_seconds}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="failure-threshold" class="mb-1 block text-sm text-gray-400">Failure threshold</label>
					<input
						id="failure-threshold"
						type="number"
						min="1"
						bind:value={healthConfig.failure_threshold}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="disk-threshold" class="mb-1 block text-sm text-gray-400">Low disk threshold (%)</label>
					<input
						id="disk-threshold"
						type="number"
						min="1"
						max="50"
						bind:value={healthConfig.low_disk_threshold_percent}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
			</div>

			<button
				onclick={saveHealth}
				disabled={savingHealth}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingHealth ? 'Saving...' : 'Save Health Settings'}
			</button>
		</section>
		<!-- Location -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Location</h2>
			<p class="mb-4 text-sm text-gray-400">
				Used for sunrise/sunset capture scheduling. Set your camera site's coordinates.
			</p>

			<div class="mb-4 grid grid-cols-2 gap-4">
				<div>
					<label for="latitude" class="mb-1 block text-sm text-gray-400">Latitude</label>
					<input
						id="latitude"
						type="number"
						step="0.0001"
						min="-90"
						max="90"
						bind:value={locationConfig.latitude}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="longitude" class="mb-1 block text-sm text-gray-400">Longitude</label>
					<input
						id="longitude"
						type="number"
						step="0.0001"
						min="-180"
						max="180"
						bind:value={locationConfig.longitude}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
			</div>

			<button
				onclick={saveLocation}
				disabled={savingLocation}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingLocation ? 'Saving...' : 'Save Location'}
			</button>
		</section>

		<!-- go2rtc -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">go2rtc</h2>
			<p class="mb-4 text-sm text-gray-400">
				Connect to an external go2rtc server for stream discovery, live MSE video, and HTTP snapshot capture.
			</p>

			<div class="mb-4">
				<label for="go2rtc-url" class="mb-1 block text-sm text-gray-400">Server URL</label>
				<input
					id="go2rtc-url"
					type="text"
					bind:value={go2rtcConfig.url}
					placeholder="http://192.168.1.100:1984"
					class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
			</div>

			{#if go2rtcTestResult}
				<p class="mb-3 text-sm {go2rtcTestResult.startsWith('Connected') ? 'text-green-400' : 'text-red-400'}">{go2rtcTestResult}</p>
			{/if}

			<div class="flex gap-2">
				<button
					onclick={testGo2rtc}
					disabled={testingGo2rtc || !go2rtcConfig.url}
					class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50"
				>
					{testingGo2rtc ? 'Testing...' : 'Test Connection'}
				</button>
				<button
					onclick={saveGo2rtc}
					disabled={savingGo2rtc}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingGo2rtc ? 'Saving...' : 'Save'}
				</button>
			</div>
		</section>

		<!-- Jobs -->
		<section class="space-y-6">
			<h2 class="text-xl font-semibold text-white">Jobs</h2>

			<!-- Capture Gap Alerting -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h3 class="mb-2 text-lg font-medium text-white">Capture Gap Alerting</h3>
				<p class="mb-4 text-sm text-gray-400">
					Alert when no frame is captured within 3× a profile's configured interval. Checks run every 60 minutes.
				</p>
				<label class="mb-4 flex items-center gap-3">
					<input
						type="checkbox"
						bind:checked={captureGapConfig.enabled}
						class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
					/>
					<span class="text-sm text-gray-200">Enable capture gap alerting</span>
				</label>
				<button
					onclick={saveCaptureGap}
					disabled={savingCaptureGap}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingCaptureGap ? 'Saving...' : 'Save'}
				</button>
			</div>

			<!-- Data Cleanup -->
			<div>
				<h3 class="mb-2 text-lg font-medium text-white">Data Cleanup</h3>
				<p class="mb-4 text-sm text-gray-400">
					Configure per-profile cleanup schedules to automatically remove old captures and timelapses.
				</p>
				<CleanupScheduleManager />
			</div>
		</section>
	{/if}
</div>
