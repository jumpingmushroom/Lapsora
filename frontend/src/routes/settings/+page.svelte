<script lang="ts">
	import { api } from '$lib/api';
	import { setUse24h } from '$lib/utils';
	import type { NotificationURL, NotificationEventsConfig, HealthConfig, LocationConfig, CaptureGapConfig, Go2rtcConfig, TimeFormatConfig, HomeAssistantConfig, PrusaLinkConfig } from '$lib/types';
	import CleanupScheduleManager from '$lib/components/CleanupScheduleManager.svelte';

	let activeTab = $state<'general' | 'notifications' | 'maintenance' | 'integrations'>('general');

	let urls = $state<NotificationURL[]>([]);
	let events = $state<NotificationEventsConfig>({
		capture_failure: true,
		stream_unhealthy: true,
		stream_recovered: true,
		timelapse_started: true,
		timelapse_complete: true,
		timelapse_failure: true,
		timelapse_cancelled: true,
		retention_summary: false,
		low_disk_space: true,
		capture_gap: true,
		print_started: false,
		print_finished: true,
		print_failed: true
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

	let timeFormatConfig = $state<TimeFormatConfig>({ use_24h: false });
	let savingTimeFormat = $state(false);

	let haConfig = $state<HomeAssistantConfig>({ base_url: '', connected: false });
	let haToken = $state('');
	let savingHA = $state(false);
	let testingHA = $state(false);
	let haTestResult = $state<string | null>(null);

	let prusaConfig = $state<PrusaLinkConfig>({
		base_url: '', username: 'maker', profile_id: null, poll_interval_seconds: 10,
		generate_on_finish: true, generate_on_cancel: false, fps: 24, format: 'mp4',
		enabled: true, connected: false
	});
	let prusaPassword = $state('');
	let prusaProfiles = $state<{ id: number; label: string }[]>([]);
	let savingPrusa = $state(false);
	let testingPrusa = $state(false);
	let prusaTestResult = $state<string | null>(null);

	let loading = $state(true);
	let newLabel = $state('');
	let newUrl = $state('');
	let testingId = $state<number | null>(null);
	let savingEvents = $state(false);
	let savingHealth = $state(false);
	let savingLocation = $state(false);

	$effect(() => {
		Promise.all([api.getNotificationSettings(), api.getHealthConfig(), api.getLocationConfig(), api.getCaptureGapConfig(), api.getGo2rtcConfig(), api.getTimeFormatConfig(), api.getHAConfig(), api.getPrusaLinkConfig()])
			.then(([notifSettings, hc, loc, gapCfg, g2rCfg, tfCfg, haCfg, prusaCfg]) => {
				urls = notifSettings.urls;
				events = notifSettings.events;
				healthConfig = hc;
				locationConfig = loc;
				captureGapConfig = gapCfg;
				go2rtcConfig = g2rCfg;
				timeFormatConfig = tfCfg;
				haConfig = haCfg;
				prusaConfig = prusaCfg;
			})
			.finally(() => {
				loading = false;
			});
		loadPrusaProfiles();
	});

	async function loadPrusaProfiles() {
		try {
			const streams = await api.getStreams();
			const lists = await Promise.all(streams.map((s) => api.getStreamProfiles(s.id)));
			prusaProfiles = streams.flatMap((s, i) => lists[i].map((p) => ({ id: p.id, label: `${s.name} / ${p.name}` })));
		} catch {
			prusaProfiles = [];
		}
	}

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
		try {
			await api.updateNotificationEvents(events);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save event settings');
		} finally {
			savingEvents = false;
		}
	}

	async function saveHealth() {
		savingHealth = true;
		try {
			await api.updateHealthConfig(healthConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save health settings');
		} finally {
			savingHealth = false;
		}
	}

	async function saveLocation() {
		savingLocation = true;
		try {
			await api.updateLocationConfig(locationConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save location');
		} finally {
			savingLocation = false;
		}
	}

	async function saveCaptureGap() {
		savingCaptureGap = true;
		try {
			await api.updateCaptureGapConfig(captureGapConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save capture gap settings');
		} finally {
			savingCaptureGap = false;
		}
	}

	async function saveGo2rtc() {
		savingGo2rtc = true;
		go2rtcTestResult = null;
		try {
			await api.updateGo2rtcConfig(go2rtcConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save go2rtc config');
		} finally {
			savingGo2rtc = false;
		}
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

	async function saveTimeFormat() {
		savingTimeFormat = true;
		try {
			await api.updateTimeFormatConfig(timeFormatConfig);
			setUse24h(timeFormatConfig.use_24h);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save time format');
		} finally {
			savingTimeFormat = false;
		}
	}

	async function saveHA() {
		savingHA = true;
		haTestResult = null;
		try {
			const payload: { base_url: string; token?: string } = { base_url: haConfig.base_url };
			if (haToken) payload.token = haToken;
			haConfig = await api.updateHAConfig(payload);
			haToken = '';
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save Home Assistant config');
		} finally {
			savingHA = false;
		}
	}

	async function testHA() {
		testingHA = true;
		haTestResult = null;
		try {
			const payload: { base_url: string; token?: string } = { base_url: haConfig.base_url };
			if (haToken) payload.token = haToken;
			const result = await api.testHAConnection(payload);
			haTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
		} catch (err) {
			haTestResult = err instanceof Error ? err.message : 'Test failed';
		}
		testingHA = false;
	}

	function prusaPayload(): PrusaLinkConfig {
		const payload = { ...prusaConfig };
		if (prusaPassword) payload.password = prusaPassword;
		else delete payload.password;
		return payload;
	}

	async function savePrusa() {
		savingPrusa = true;
		prusaTestResult = null;
		try {
			prusaConfig = await api.updatePrusaLinkConfig(prusaPayload());
			prusaPassword = '';
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save PrusaLink config');
		} finally {
			savingPrusa = false;
		}
	}

	async function testPrusa() {
		testingPrusa = true;
		prusaTestResult = null;
		try {
			const result = await api.testPrusaLinkConnection(prusaPayload());
			prusaTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
		} catch (err) {
			prusaTestResult = err instanceof Error ? err.message : 'Test failed';
		}
		testingPrusa = false;
	}

	const eventLabels: Record<string, string> = {
		capture_failure: 'Capture failure',
		stream_unhealthy: 'Stream unhealthy',
		stream_recovered: 'Stream recovered',
		timelapse_started: 'Timelapse started',
		timelapse_complete: 'Timelapse complete',
		timelapse_failure: 'Timelapse failure',
		timelapse_cancelled: 'Timelapse cancelled',
		retention_summary: 'Retention summary',
		low_disk_space: 'Low disk space',
		capture_gap: 'Capture gap',
		print_started: 'Print started',
		print_finished: 'Print finished',
		print_failed: 'Print stopped/failed'
	};
</script>

<svelte:head><title>Settings - Lapsora</title></svelte:head>

<div class="space-y-8">
	<h1 class="text-3xl font-bold text-white">Settings</h1>

	<div class="flex gap-2 border-b border-gray-800">
		<button
			onclick={() => (activeTab = 'general')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'general' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>General</button>
		<button
			onclick={() => (activeTab = 'notifications')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'notifications' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>Notifications</button>
		<button
			onclick={() => (activeTab = 'maintenance')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'maintenance' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>Maintenance</button>
		<button
			onclick={() => (activeTab = 'integrations')}
			class="px-4 py-2 text-sm font-medium transition-colors {activeTab === 'integrations' ? 'border-b-2 border-blue-500 text-white' : 'text-gray-400 hover:text-gray-200'}"
		>Integrations</button>
	</div>

	{#if loading}
		<p class="text-gray-400">Loading settings...</p>
	{:else}
		{#if activeTab === 'general'}
			<!-- Display -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h2 class="mb-4 text-xl font-semibold text-white">Display</h2>
				<label class="mb-4 flex items-center gap-3">
					<input
						type="checkbox"
						bind:checked={timeFormatConfig.use_24h}
						class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
					/>
					<span class="text-sm text-gray-200">Use 24-hour time format</span>
				</label>
				<button
					onclick={saveTimeFormat}
					disabled={savingTimeFormat}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingTimeFormat ? 'Saving...' : 'Save'}
				</button>
			</section>
		{/if}

		{#if activeTab === 'notifications'}
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
		{/if}

		{#if activeTab === 'maintenance'}
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
		{/if}

		{#if activeTab === 'general'}
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

		{/if}

		{#if activeTab === 'maintenance'}
			<!-- Capture Gap Alerting -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h2 class="mb-4 text-xl font-semibold text-white">Capture Gap Alerting</h2>
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
			</section>

			<!-- Data Cleanup -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h2 class="mb-4 text-xl font-semibold text-white">Data Cleanup</h2>
				<p class="mb-4 text-sm text-gray-400">
					Configure per-profile cleanup schedules to automatically remove old captures and timelapses.
				</p>
				<CleanupScheduleManager />
			</section>
		{/if}

		{#if activeTab === 'integrations'}
			<!-- Home Assistant -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<div class="mb-4 flex items-center gap-3">
					<h2 class="text-xl font-semibold text-white">Home Assistant</h2>
					<span class="rounded-full px-2 py-0.5 text-xs {haConfig.connected ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}">
						{haConfig.connected ? 'Connected' : 'Not configured'}
					</span>
				</div>
				<p class="mb-4 text-sm text-gray-400">Read sensor entities to overlay on timelapses. Create a long-lived access token in your HA profile.</p>

				<div class="mb-4">
					<label for="ha-url" class="mb-1 block text-sm text-gray-400">Base URL</label>
					<input id="ha-url" type="text" bind:value={haConfig.base_url} placeholder="http://homeassistant.local:8123"
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>
				<div class="mb-4">
					<label for="ha-token" class="mb-1 block text-sm text-gray-400">Long-lived access token</label>
					<input id="ha-token" type="password" bind:value={haToken} placeholder={haConfig.connected ? '•••••••• (leave blank to keep)' : 'Paste token'}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>

				{#if haTestResult}
					<p class="mb-3 text-sm {haTestResult.startsWith('Connected') ? 'text-green-400' : 'text-red-400'}">{haTestResult}</p>
				{/if}

				<div class="flex gap-2">
					<button onclick={testHA} disabled={testingHA || !haConfig.base_url}
						class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50">
						{testingHA ? 'Testing...' : 'Test Connection'}
					</button>
					<button onclick={saveHA} disabled={savingHA}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50">
						{savingHA ? 'Saving...' : 'Save'}
					</button>
				</div>
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

			<!-- PrusaLink (3D-print timelapse trigger) -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<div class="mb-4 flex items-center gap-3">
					<h2 class="text-xl font-semibold text-white">3D Printing (PrusaLink)</h2>
					<span class="rounded-full px-2 py-0.5 text-xs {prusaConfig.connected ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}">
						{prusaConfig.connected ? 'Configured' : 'Not configured'}
					</span>
				</div>
				<p class="mb-4 text-sm text-gray-400">
					Poll a Prusa printer's local PrusaLink API and capture a timelapse for the duration of each print. Point a capture profile's camera at the printer, then select it below. Create a password/API access in the printer's PrusaLink settings.
				</p>

				<div class="mb-4 grid grid-cols-2 gap-4">
					<div>
						<label for="prusa-url" class="mb-1 block text-sm text-gray-400">Base URL</label>
						<input id="prusa-url" type="text" bind:value={prusaConfig.base_url} placeholder="http://prusa.local"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
					</div>
					<div>
						<label for="prusa-user" class="mb-1 block text-sm text-gray-400">Username</label>
						<input id="prusa-user" type="text" bind:value={prusaConfig.username} placeholder="maker"
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
					</div>
				</div>

				<div class="mb-4">
					<label for="prusa-pass" class="mb-1 block text-sm text-gray-400">Password</label>
					<input id="prusa-pass" type="password" bind:value={prusaPassword} placeholder={prusaConfig.connected ? '•••••••• (leave blank to keep)' : 'PrusaLink password'}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>

				<div class="mb-4 grid grid-cols-2 gap-4">
					<div>
						<label for="prusa-profile" class="mb-1 block text-sm text-gray-400">Capture profile</label>
						<select id="prusa-profile" bind:value={prusaConfig.profile_id}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
							<option value={null}>— Select a profile —</option>
							{#each prusaProfiles as p}
								<option value={p.id}>{p.label}</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="prusa-poll" class="mb-1 block text-sm text-gray-400">Poll interval (seconds)</label>
						<input id="prusa-poll" type="number" min="5" bind:value={prusaConfig.poll_interval_seconds}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
				</div>

				<div class="mb-4 grid grid-cols-2 gap-4">
					<div>
						<label for="prusa-fps" class="mb-1 block text-sm text-gray-400">Timelapse FPS</label>
						<input id="prusa-fps" type="number" min="1" bind:value={prusaConfig.fps}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
					<div>
						<label for="prusa-format" class="mb-1 block text-sm text-gray-400">Format</label>
						<select id="prusa-format" bind:value={prusaConfig.format}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
							<option value="mp4">MP4</option>
							<option value="webm">WebM</option>
							<option value="gif">GIF</option>
						</select>
					</div>
				</div>

				<div class="mb-4 space-y-2">
					<label class="flex items-center gap-3">
						<input type="checkbox" bind:checked={prusaConfig.enabled}
							class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
						<span class="text-sm text-gray-200">Enable print-triggered capture</span>
					</label>
					<label class="flex items-center gap-3">
						<input type="checkbox" bind:checked={prusaConfig.generate_on_finish}
							class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
						<span class="text-sm text-gray-200">Auto-generate timelapse when a print finishes</span>
					</label>
					<label class="flex items-center gap-3">
						<input type="checkbox" bind:checked={prusaConfig.generate_on_cancel}
							class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
						<span class="text-sm text-gray-200">Also generate on cancelled/failed prints</span>
					</label>
				</div>

				{#if prusaTestResult}
					<p class="mb-3 text-sm {prusaTestResult.startsWith('Connected') ? 'text-green-400' : 'text-red-400'}">{prusaTestResult}</p>
				{/if}

				<div class="flex gap-2">
					<button onclick={testPrusa} disabled={testingPrusa || !prusaConfig.base_url}
						class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50">
						{testingPrusa ? 'Testing...' : 'Test Connection'}
					</button>
					<button onclick={savePrusa} disabled={savingPrusa}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50">
						{savingPrusa ? 'Saving...' : 'Save'}
					</button>
				</div>
			</section>
		{/if}
	{/if}
</div>
