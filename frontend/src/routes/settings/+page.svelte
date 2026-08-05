<script lang="ts">
	import { api } from '$lib/api';
	import { setUse24h } from '$lib/utils';
	import type { NotificationURL, NotificationEventsConfig, HealthConfig, LocationConfig, CaptureGapConfig, Go2rtcConfig, TimeFormatConfig, HomeAssistantConfig, PrusaLinkConfig, HAEntity, HASensor } from '$lib/types';
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
		base_url: '', username: 'maker', stream_id: null, poll_interval_seconds: 10,
		generate_on_finish: true, generate_on_cancel: false, enabled: true,
		clip_seconds: 20, clip_fps: 25, default_interval_seconds: 10,
		min_interval_seconds: 2, max_interval_seconds: 120,
		timestamp_overlay: true, logo_overlay: false, deflicker: 'medium', quality: 90,
		ha_sensors: null, configured: false, connected: false
	});
	let prusaPassword = $state('');
	let prusaStreams = $state<{ id: number; name: string }[]>([]);
	let haEntities = $state<HAEntity[]>([]);
	let savingPrusa = $state(false);
	let testingPrusa = $state(false);
	let prusaTestResult = $state<string | null>(null);

	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let logoInfo = $state<{ exists: boolean; uploaded_at: string | null }>({ exists: false, uploaded_at: null });
	let logoCacheBust = $state(0);
	let uploadingLogo = $state(false);

	async function onLogoSelected(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		uploadingLogo = true;
		try {
			logoInfo = await api.uploadLogo(file);
			logoCacheBust++;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to upload logo');
		} finally {
			uploadingLogo = false;
			input.value = '';
		}
	}

	async function removeLogo() {
		if (!confirm('Remove the uploaded logo?')) return;
		try {
			await api.deleteLogo();
			logoInfo = { exists: false, uploaded_at: null };
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete logo');
		}
	}

	let newLabel = $state('');
	let newUrl = $state('');
	let testingId = $state<number | null>(null);
	let savingEvents = $state(false);
	let savingHealth = $state(false);
	let savingLocation = $state(false);

	$effect(() => {
		Promise.all([api.getNotificationSettings(), api.getHealthConfig(), api.getLocationConfig(), api.getCaptureGapConfig(), api.getGo2rtcConfig(), api.getTimeFormatConfig(), api.getHAConfig(), api.getPrusaLinkConfig(), api.getLogo()])
			.then(([notifSettings, hc, loc, gapCfg, g2rCfg, tfCfg, haCfg, prusaCfg, logoCfg]) => {
				urls = notifSettings.urls;
				events = notifSettings.events;
				healthConfig = hc;
				locationConfig = loc;
				captureGapConfig = gapCfg;
				go2rtcConfig = g2rCfg;
				timeFormatConfig = tfCfg;
				haConfig = haCfg;
				prusaConfig = prusaCfg;
				logoInfo = logoCfg;
				loadError = null;
			})
			.catch((err) => {
				// Without this, a failed load silently leaves the hardcoded
				// default $state values in place; saving any section would then
				// overwrite the real stored config with those defaults.
				loadError = err instanceof Error ? err.message : 'Failed to load settings';
			})
			.finally(() => {
				loading = false;
			});
		loadPrusaStreams();
	});

	async function loadPrusaStreams() {
		try {
			const streams = await api.getStreams();
			prusaStreams = streams.map((s) => ({ id: s.id, name: s.name }));
		} catch {
			prusaStreams = [];
		}
		// Sensor list for the overlay picker; absent/unconfigured HA is fine.
		try {
			haEntities = await api.getHAEntities();
		} catch {
			haEntities = [];
		}
	}

	function prusaSensorIds(): string[] {
		try {
			return (prusaConfig.ha_sensors ? (JSON.parse(prusaConfig.ha_sensors) as HASensor[]) : []).map((s) => s.entity_id);
		} catch {
			return [];
		}
	}

	function togglePrusaSensor(e: HAEntity) {
		const ids = prusaSensorIds();
		let list: HASensor[];
		try {
			list = prusaConfig.ha_sensors ? (JSON.parse(prusaConfig.ha_sensors) as HASensor[]) : [];
		} catch {
			list = [];
		}
		if (ids.includes(e.entity_id)) {
			list = list.filter((s) => s.entity_id !== e.entity_id);
		} else {
			list = [...list, { entity_id: e.entity_id, label: e.friendly_name, unit: e.unit, icon: '' }];
		}
		prusaConfig.ha_sensors = list.length ? JSON.stringify(list) : null;
	}

	async function addUrl() {
		if (!newLabel.trim() || !newUrl.trim()) return;
		try {
			const nu = await api.addNotificationURL({ label: newLabel.trim(), url: newUrl.trim() });
			urls = [...urls, nu];
			newLabel = '';
			newUrl = '';
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to add notification URL');
		}
	}

	async function removeUrl(id: number) {
		try {
			await api.deleteNotificationURL(id);
			urls = urls.filter((u) => u.id !== id);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to remove notification URL');
		}
	}

	async function toggleUrl(nu: NotificationURL) {
		try {
			const updated = await api.updateNotificationURL(nu.id, { enabled: !nu.enabled });
			urls = urls.map((u) => (u.id === updated.id ? updated : u));
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update notification URL');
		}
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
			await api.updateGo2rtcConfig({ url: go2rtcConfig.url });
			// Re-fetch to refresh the live health badge against the saved URL.
			go2rtcConfig = await api.getGo2rtcConfig();
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
			const result = await api.testGo2rtcServer({ url: go2rtcConfig.url });
			go2rtcTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
			go2rtcConfig = { ...go2rtcConfig, configured: !!go2rtcConfig.url, connected: result.success };
		} catch (err) {
			go2rtcTestResult = err instanceof Error ? err.message : 'Test failed';
			go2rtcConfig = { ...go2rtcConfig, connected: false };
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
	{:else if loadError}
		<div class="rounded-xl border border-red-800 bg-red-950/40 p-6">
			<p class="font-medium text-red-300">Couldn't load settings</p>
			<p class="mt-1 text-sm text-red-400">{loadError}</p>
			<p class="mt-2 text-sm text-gray-400">
				The form is hidden to avoid overwriting your saved configuration with defaults. Reload the page to try again.
			</p>
		</div>
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

			<!-- Branding -->
			<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h2 class="mb-4 text-xl font-semibold text-white">Branding</h2>
				<p class="mb-4 text-sm text-gray-400">
					Upload a logo to watermark onto generated timelapses. PNG with transparency works best. Enable it per-timelapse in the generate dialog or a schedule, where you pick the corner, size, and opacity.
				</p>

				<div class="flex items-center gap-4">
					{#if logoInfo.exists}
						<img
							src={`/static/logos/logo.png?v=${logoCacheBust}`}
							alt="Current logo"
							class="h-16 w-16 rounded-lg border border-gray-700 bg-[length:16px_16px] object-contain p-1"
							style="background-image: linear-gradient(45deg,#374151 25%,transparent 25%),linear-gradient(-45deg,#374151 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#374151 75%),linear-gradient(-45deg,transparent 75%,#374151 75%); background-position:0 0,0 8px,8px -8px,-8px 0;"
						/>
					{:else}
						<div class="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed border-gray-700 text-xs text-gray-500">None</div>
					{/if}
					<div class="flex flex-col gap-2">
						<label class="cursor-pointer rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 {uploadingLogo ? 'opacity-50' : ''}">
							{uploadingLogo ? 'Uploading...' : logoInfo.exists ? 'Replace logo' : 'Upload logo'}
							<input type="file" accept="image/*" class="hidden" onchange={onLogoSelected} disabled={uploadingLogo} />
						</label>
						{#if logoInfo.exists}
							<button
								onclick={removeLogo}
								class="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
							>
								Remove
							</button>
						{/if}
					</div>
				</div>
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
					{#if !haConfig.configured}
						<span class="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-400">Not configured</span>
					{:else if haConfig.credential_error}
						<span class="rounded-full bg-amber-900 px-2 py-0.5 text-xs text-amber-300">⚠ Re-auth needed</span>
					{:else if haConfig.connected}
						<span class="rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300">Connected</span>
					{:else}
						<span class="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300">Unreachable</span>
					{/if}
				</div>
				{#if haConfig.credential_error}
					<p class="mb-4 rounded-lg border border-amber-800 bg-amber-950/50 p-3 text-sm text-amber-300">
						Stored token can't be decrypted (the encryption key changed). Re-enter your token to restore the connection.
					</p>
				{/if}
				<p class="mb-4 text-sm text-gray-400">Read sensor entities to overlay on timelapses. Create a long-lived access token in your HA profile.</p>

				<div class="mb-4">
					<label for="ha-url" class="mb-1 block text-sm text-gray-400">Base URL</label>
					<input id="ha-url" type="text" bind:value={haConfig.base_url} placeholder="http://homeassistant.local:8123"
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>
				<div class="mb-4">
					<label for="ha-token" class="mb-1 block text-sm text-gray-400">Long-lived access token</label>
					<input id="ha-token" type="password" bind:value={haToken} placeholder={haConfig.configured ? (haConfig.credential_error ? 'Re-enter to restore the connection' : '•••••••• (leave blank to keep)') : 'Paste token'}
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
				<div class="mb-4 flex items-center gap-3">
					<h2 class="text-xl font-semibold text-white">go2rtc</h2>
					{#if !go2rtcConfig.configured}
						<span class="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-400">Not configured</span>
					{:else if go2rtcConfig.connected}
						<span class="rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300">Connected</span>
					{:else}
						<span class="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300">Unreachable</span>
					{/if}
				</div>
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
					{#if !prusaConfig.configured}
						<span class="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-400">Not configured</span>
					{:else if prusaConfig.credential_error}
						<span class="rounded-full bg-amber-900 px-2 py-0.5 text-xs text-amber-300">⚠ Re-auth needed</span>
					{:else if prusaConfig.connected}
						<span class="rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300">Connected</span>
					{:else}
						<span class="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300">Unreachable</span>
					{/if}
				</div>
				{#if prusaConfig.credential_error}
					<p class="mb-4 rounded-lg border border-amber-800 bg-amber-950/50 p-3 text-sm text-amber-300">
						Stored password can't be decrypted (the encryption key changed). Re-enter your password to restore the connection.
					</p>
				{/if}
				<p class="mb-4 text-sm text-gray-400">
					Poll a Prusa printer's local PrusaLink API and capture a timelapse for each print. Pick the camera pointed at the printer — capture interval is computed per print from the printer's time estimate, so short and overnight prints both render to the clip length below.
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
					<input id="prusa-pass" type="password" bind:value={prusaPassword} placeholder={prusaConfig.configured ? (prusaConfig.credential_error ? 'Re-enter to restore the connection' : '•••••••• (leave blank to keep)') : 'PrusaLink password'}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none" />
				</div>

				<div class="mb-4 grid grid-cols-2 gap-4">
					<div>
						<label for="prusa-stream" class="mb-1 block text-sm text-gray-400">Camera</label>
						<select id="prusa-stream" bind:value={prusaConfig.stream_id}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
							<option value={null}>— Select a camera —</option>
							{#each prusaStreams as s}
								<option value={s.id}>{s.name}</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="prusa-poll" class="mb-1 block text-sm text-gray-400">Poll interval (seconds)</label>
						<input id="prusa-poll" type="number" min="5" bind:value={prusaConfig.poll_interval_seconds}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
				</div>

				<div class="mb-4 grid grid-cols-3 gap-4">
					<div>
						<label for="prusa-clip-len" class="mb-1 block text-sm text-gray-400">Clip length (seconds)</label>
						<input id="prusa-clip-len" type="number" min="1" max="300" bind:value={prusaConfig.clip_seconds}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
					<div>
						<label for="prusa-clip-fps" class="mb-1 block text-sm text-gray-400">Clip FPS</label>
						<input id="prusa-clip-fps" type="number" min="1" max="120" bind:value={prusaConfig.clip_fps}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
					<div>
						<label for="prusa-default-int" class="mb-1 block text-sm text-gray-400">Fallback interval (s)</label>
						<input id="prusa-default-int" type="number" min="1" bind:value={prusaConfig.default_interval_seconds}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
					</div>
				</div>

				<details class="mb-4 rounded-lg border border-gray-800 p-3">
					<summary class="cursor-pointer text-sm text-gray-400">Advanced: interval clamp</summary>
					<div class="mt-3 grid grid-cols-2 gap-4">
						<div>
							<label for="prusa-min-int" class="mb-1 block text-sm text-gray-400">Min interval (s)</label>
							<input id="prusa-min-int" type="number" min="1" bind:value={prusaConfig.min_interval_seconds}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
						</div>
						<div>
							<label for="prusa-max-int" class="mb-1 block text-sm text-gray-400">Max interval (s)</label>
							<input id="prusa-max-int" type="number" min="1" bind:value={prusaConfig.max_interval_seconds}
								class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none" />
						</div>
					</div>
				</details>

				<details class="mb-4 rounded-lg border border-gray-800 p-3">
					<summary class="cursor-pointer text-sm text-gray-400">Overlays &amp; render</summary>
					<div class="mt-3 space-y-3">
						<div class="grid grid-cols-2 gap-4">
							<div>
								<label for="prusa-quality" class="mb-1 block text-sm text-gray-400">Capture quality ({prusaConfig.quality})</label>
								<input id="prusa-quality" type="range" min="1" max="100" bind:value={prusaConfig.quality} class="w-full" />
							</div>
							<div>
								<label for="prusa-deflicker" class="mb-1 block text-sm text-gray-400">Deflicker</label>
								<select id="prusa-deflicker" bind:value={prusaConfig.deflicker}
									class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none">
									<option value="off">Off</option>
									<option value="light">Light</option>
									<option value="medium">Medium</option>
									<option value="heavy">Heavy</option>
								</select>
							</div>
						</div>
						<label class="flex items-center gap-3">
							<input type="checkbox" bind:checked={prusaConfig.timestamp_overlay}
								class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
							<span class="text-sm text-gray-200">Timestamp overlay</span>
						</label>
						<label class="flex items-center gap-3">
							<input type="checkbox" bind:checked={prusaConfig.logo_overlay}
								class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
							<span class="text-sm text-gray-200">Logo overlay</span>
						</label>
						{#if haEntities.length}
							<div>
								<span class="mb-1 block text-sm text-gray-400">Home Assistant sensor overlay</span>
								<div class="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-gray-800 p-2">
									{#each haEntities as e}
										<label class="flex items-center gap-3">
											<input type="checkbox" checked={prusaSensorIds().includes(e.entity_id)}
												onchange={() => togglePrusaSensor(e)}
												class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600" />
											<span class="text-sm text-gray-200">{e.friendly_name ?? e.entity_id}</span>
										</label>
									{/each}
								</div>
							</div>
						{:else}
							<p class="text-xs text-gray-500">Configure Home Assistant above to add sensor overlays.</p>
						{/if}
					</div>
				</details>

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
