<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import type { Stream, Profile, ProfileCreate, ProfileUpdate, Capture, TestResult, HASensor } from '$lib/types';
	import { formatInterval, formatDateTime, timeAgo, healthDotClass } from '$lib/utils';
	import ProfileForm from '$lib/components/ProfileForm.svelte';
	import MsePlayer from '$lib/components/MsePlayer.svelte';
	import CapturePreview from '$lib/components/CapturePreview.svelte';
	import CameraDiagnostic from '$lib/components/CameraDiagnostic.svelte';
	import AddCapturePlanWizard from '$lib/components/AddCapturePlanWizard.svelte';
	import RenderWizard from '$lib/components/RenderWizard.svelte';
	import CameraRenderSchedules from '$lib/components/CameraRenderSchedules.svelte';
	import CameraPrints from '$lib/components/CameraPrints.svelte';
	import { defaultRenderDraft } from '$lib/renderDraft';
	import type { RenderDraft } from '$lib/renderDraft';

	let id = $derived(Number($page.params.id));

	let stream = $state<Stream | null>(null);
	let profiles = $state<Profile[]>([]);
	let captures = $state<Capture[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Capture preview viewer
	const CAPTURES_PAGE = 12;
	let previewOpen = $state(false);
	let previewIndex = $state(0);
	let capturesProfileId = $state<number | null>(null);
	let allCapturesLoaded = $state(false);
	let loadingMore = $state(false);

	function haSensorsOf(profile: Profile): HASensor[] {
		try { return profile.ha_sensors ? JSON.parse(profile.ha_sensors) : []; }
		catch { return []; }
	}

	async function loadMoreCaptures() {
		if (loadingMore || allCapturesLoaded || capturesProfileId == null) return;
		loadingMore = true;
		try {
			const more = await api.getProfileCaptures(capturesProfileId, CAPTURES_PAGE, captures.length);
			captures = [...captures, ...more];
			if (more.length < CAPTURES_PAGE) allCapturesLoaded = true;
		} catch {
			// ignore — keep what we have
		} finally {
			loadingMore = false;
		}
	}

	// Edit form
	let editName = $state('');
	let editEnabled = $state(true);
	let newUrl = $state('');
	let saving = $state(false);
	let saveMsg = $state('');

	// Connection test
	let testing = $state(false);
	let testResult = $state<TestResult | null>(null);
	let testCodec = $derived(testResult?.details?.codec as string | undefined);
	let testResolution = $derived(testResult?.details?.resolution as string | undefined);
	let testFps = $derived(testResult?.details?.fps as string | undefined);

	// Delete stream
	let confirmDeleteStream = $state(false);
	let deletingStream = $state(false);

	// Creating a plan is a guided flow; editing one stays a direct form.
	let showPlanWizard = $state(false);
	let profileLoading = $state(false);

	// Profile actions
	let editingProfile = $state<Profile | null>(null);
	let confirmDelete = $state<Profile | null>(null);
	let activeMenu = $state<number | null>(null);
	let replaceMode = $state(false);

	// Preview
	let previewKey = $state(0);
	let previewSrc = $derived(`${api.getStreamPreviewUrl(id)}?t=${previewKey}`);

	// Anything that can change the capture chain bumps this, so the diagnostic
	// re-answers instead of showing a stale verdict.
	let diagnosticKey = $state(0);

	// Live view (go2rtc)
	let liveWsUrl = $state<string | null>(null);
	let showLiveView = $state(false);

	$effect(() => {
		const currentId = id;
		// Guard against a slow response for a previous stream resolving after the
		// user navigated away and clobbering the new stream's data.
		let cancelled = false;
		loading = true;
		error = null;
		previewOpen = false;
		capturesProfileId = null;
		allCapturesLoaded = false;
		captures = [];
		testResult = null;
		confirmDeleteStream = false;

		Promise.all([
			api.getStream(currentId),
			api.getStreamProfiles(currentId)
		])
			.then(([s, p]) => {
				if (cancelled) return;
				stream = s;
				editName = s.name;
				editEnabled = s.enabled;
				profiles = p;
				if (p.length > 0) {
					capturesProfileId = p[0].id;
					api.getProfileCaptures(p[0].id, CAPTURES_PAGE)
						.then((c) => {
							if (cancelled) return;
							captures = c;
							allCapturesLoaded = c.length < CAPTURES_PAGE;
						})
						.catch(() => {});
				}
			})
			.catch((err) => { if (!cancelled) error = err instanceof Error ? err.message : 'Failed to load'; })
			.finally(() => { if (!cancelled) loading = false; });

		return () => { cancelled = true; };
	});

	// Auto-refresh preview. Each refresh triggers a live server-side frame grab,
	// so keep it gentle and skip it while the tab is hidden.
	$effect(() => {
		const interval = setInterval(() => {
			if (!document.hidden) previewKey++;
		}, 15000);
		return () => clearInterval(interval);
	});

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		saveMsg = '';
		try {
			const updated = await api.updateStream(id, {
				name: editName,
				enabled: editEnabled,
				url: newUrl || undefined
			});
			stream = updated;
			newUrl = '';
			diagnosticKey++;
			saveMsg = 'Saved';
			setTimeout(() => { saveMsg = ''; }, 2000);
		} catch (err) {
			saveMsg = err instanceof Error ? err.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function handleTest() {
		testing = true;
		testResult = null;
		try {
			testResult = await api.testStream(id);
		} catch (err) {
			testResult = { success: false, message: err instanceof Error ? err.message : 'Test failed' };
		} finally {
			testing = false;
		}
	}

	async function handleDeleteStream() {
		deletingStream = true;
		try {
			await api.deleteStream(id);
			goto('/streams');
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete camera');
			deletingStream = false;
		}
	}

	// Renders for a specific plan, opened from its menu — the plan is implied,
	// so the wizard skips straight to the schedule question.
	let renderWizardDraft = $state<RenderDraft | null>(null);
	// Set when the wizard was opened for one specific plan; null when the
	// camera's plans should all be offered.
	let renderWizardPlanFixed = $state(false);
	let scheduleKey = $state(0);

	// A printer-bound camera leads with its prints: they are what it is for.
	// Capture plans stay available below, so an ordinary timelapse of the
	// printer is still possible alongside the per-print videos.
	let printerBound = $derived(stream?.printer_bound === true);

	function openRenderWizard(profile: Profile) {
		renderWizardDraft = defaultRenderDraft('repeat', profile.id);
		renderWizardPlanFixed = true;
		activeMenu = null;
	}

	/** The diagnostic named a gap; open whatever closes it. */
	async function runDiagnosticAction(action: string) {
		if (action === 'open_printer_settings') {
			goto('/settings');
		} else if (action === 'add_plan') {
			openPlanWizard();
		} else if (action === 'add_schedule') {
			openRenderWizardForCamera();
		} else if (action === 'enable_camera') {
			try {
				stream = await api.updateStream(id, { enabled: true });
				editEnabled = true;
				diagnosticKey++;
			} catch (err) {
				alert(err instanceof Error ? err.message : 'Failed to enable camera');
			}
		}
	}

	function openRenderWizardForCamera() {
		renderWizardDraft = defaultRenderDraft('repeat', profiles[0]?.id ?? 0);
		renderWizardPlanFixed = false;
	}

	function openPlanWizard() {
		showPlanWizard = true;
		editingProfile = null;
	}

	async function reloadPlans() {
		profiles = await api.getStreamProfiles(id);
		diagnosticKey++;
		// The plan wizard can create a schedule on its way out, so the
		// schedules list has to re-ask too.
		scheduleKey++;
	}

	async function handleUpdateProfile(data: ProfileCreate | ProfileUpdate) {
		if (!editingProfile) return;
		profileLoading = true;
		try {
			await api.updateProfile(editingProfile.id, data as ProfileUpdate);
			profiles = await api.getStreamProfiles(id);
			diagnosticKey++;
			editingProfile = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update capture plan');
		} finally {
			profileLoading = false;
		}
	}

	async function handleDeleteProfile() {
		if (!confirmDelete) return;
		profileLoading = true;
		const shouldReplace = replaceMode;
		try {
			await api.deleteProfile(confirmDelete.id);
			profiles = await api.getStreamProfiles(id);
			diagnosticKey++;
			confirmDelete = null;
			replaceMode = false;
			if (shouldReplace) {
				openPlanWizard();
			}
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete capture plan');
		} finally {
			profileLoading = false;
		}
	}

	async function handleDuplicateProfile(profile: Profile) {
		profileLoading = true;
		activeMenu = null;
		try {
			await api.createProfile(id, {
				name: profile.name + ' (copy)',
				interval_seconds: profile.interval_seconds,
				resolution_width: profile.resolution_width,
				resolution_height: profile.resolution_height,
				quality: profile.quality,
				hdr_enabled: profile.hdr_enabled,
				weather_enabled: profile.weather_enabled,
				capture_mode: profile.capture_mode,
				active_start_time: profile.active_start_time,
				active_end_time: profile.active_end_time,
				sun_offset_minutes: profile.sun_offset_minutes,
				sun_events: profile.sun_events,
				ir_only: profile.ir_only,
				ir_chroma_threshold: profile.ir_chroma_threshold,
				ha_sensors: profile.ha_sensors
			});
			profiles = await api.getStreamProfiles(id);
			diagnosticKey++;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to duplicate capture plan');
		} finally {
			profileLoading = false;
		}
	}

	async function toggleProfile(profile: Profile) {
		try {
			if (profile.enabled) {
				await api.disableProfile(profile.id);
			} else {
				await api.enableProfile(profile.id);
			}
			profiles = await api.getStreamProfiles(id);
			diagnosticKey++;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to toggle capture plan');
		}
	}
</script>

<svelte:head><title>{stream?.name ?? 'Camera'} - Lapsora</title></svelte:head>

{#if loading}
	<p class="text-gray-400">Loading camera...</p>
{:else if error}
	<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
		<p class="text-sm text-red-400">{error}</p>
	</div>
{:else if stream}
	<div class="space-y-6">
		<div class="flex items-center gap-3">
			<a href="/streams" class="text-gray-400 hover:text-gray-200">
				<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
				</svg>
			</a>
			<h1 class="text-3xl font-bold text-white">{stream.name}</h1>
			<span class="rounded-full px-2 py-0.5 text-xs font-medium {stream.enabled ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">
				{stream.enabled ? 'Enabled' : 'Disabled'}
			</span>
		</div>

		<CameraDiagnostic streamId={id} refreshKey={diagnosticKey} onaction={runDiagnosticAction} />

		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<!-- Live Preview -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<div class="mb-2 flex items-center justify-between">
					<div class="flex items-center gap-2">
						<span class="h-2.5 w-2.5 rounded-full {healthDotClass(stream.health_status)}" title={stream.health_status}></span>
						<h2 class="text-lg font-semibold text-gray-100">Live Preview</h2>
					</div>
					{#if stream.source_type === 'go2rtc'}
						<button
							onclick={async () => {
								if (showLiveView) {
									showLiveView = false;
									liveWsUrl = null;
								} else {
									try {
										const data = await api.getStreamLiveUrl(id);
										liveWsUrl = data.ws_url;
										showLiveView = true;
									} catch (err) {
										console.error('Failed to start live view', err);
										alert('Could not start live view. Check that go2rtc is reachable.');
									}
								}
							}}
							class="rounded px-3 py-1 text-xs font-medium transition-colors {showLiveView ? 'bg-red-900 text-red-300' : 'bg-green-900 text-green-300'}"
						>
							{showLiveView ? 'Stop Live' : 'Live View'}
						</button>
					{/if}
				</div>
				<div class="mb-3 flex flex-wrap items-center gap-x-1.5 text-xs text-gray-400">
					<span class="capitalize {stream.health_status === 'unhealthy' ? 'text-red-400' : stream.health_status === 'healthy' ? 'text-green-400' : ''}">{stream.health_status}</span>
					<span class="text-gray-600">·</span>
					<span>Checked {timeAgo(stream.last_checked_at)}</span>
					{#if stream.consecutive_failures > 0}
						<span class="text-gray-600">·</span>
						<span class="text-amber-400">{stream.consecutive_failures} fail{stream.consecutive_failures !== 1 ? 's' : ''}</span>
					{/if}
					{#if testCodec || testResolution}
						<span class="text-gray-600">·</span>
						<span>{[testCodec, testResolution].filter(Boolean).join(' ')}</span>
					{/if}
				</div>
				{#if showLiveView && liveWsUrl}
					<MsePlayer wsUrl={liveWsUrl} />
				{:else}
					<div class="aspect-video w-full overflow-hidden rounded-lg bg-black">
						<img
							src={previewSrc}
							alt="{stream.name} live preview"
							class="h-full w-full object-contain"
							onerror={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3'; }}
							onload={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '1'; }}
						/>
					</div>
					<p class="mt-2 text-xs text-gray-500">Auto-refreshes every 15 seconds</p>
				{/if}
			</div>

			<!-- Edit Form -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<h2 class="mb-3 text-lg font-semibold text-gray-100">Settings</h2>
				<form onsubmit={handleSave} class="space-y-4">
					<div>
						<label for="edit-name" class="mb-1 block text-sm font-medium text-gray-300">Name</label>
						<input
							id="edit-name"
							type="text"
							bind:value={editName}
							required
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					{#if stream.source_type !== 'go2rtc'}
					<div>
						<label for="edit-url" class="mb-1 block text-sm font-medium text-gray-300">New RTSP URL (leave blank to keep current)</label>
						<input
							id="edit-url"
							type="text"
							bind:value={newUrl}
							placeholder="rtsp://..."
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 truncate text-xs text-gray-500" title={stream.url_masked ?? undefined}>Current: {stream.url_masked ?? '—'}</p>
					</div>
				{:else}
					<div>
						<span class="mb-1 block text-sm font-medium text-gray-300">Source</span>
						<span class="text-sm text-gray-400">go2rtc: {stream.go2rtc_name}</span>
					</div>
				{/if}
					<label class="flex items-center gap-2">
						<input
							type="checkbox"
							bind:checked={editEnabled}
							class="rounded border-gray-700 bg-gray-800 text-blue-500 focus:ring-blue-500"
						/>
						<span class="text-sm text-gray-300">Enabled</span>
					</label>
					<div class="flex flex-wrap items-center gap-3">
						<button
							type="submit"
							disabled={saving}
							class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
						>
							{saving ? 'Saving...' : 'Save Changes'}
						</button>
						<button
							type="button"
							onclick={handleTest}
							disabled={testing}
							class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50"
						>
							{testing ? 'Testing...' : 'Test Connection'}
						</button>
						{#if saveMsg}
							<span class="text-sm {saveMsg === 'Saved' ? 'text-green-400' : 'text-red-400'}">{saveMsg}</span>
						{/if}
					</div>
					{#if testResult}
						<div class="rounded-lg border p-3 text-sm {testResult.success ? 'border-green-800 bg-green-950/40 text-green-300' : 'border-red-800 bg-red-950/40 text-red-300'}">
							<p>{testResult.message}</p>
							{#if testResult.success && (testCodec || testResolution || testFps)}
								<p class="mt-1 text-xs text-gray-400">
									{[testCodec, testResolution, testFps && `${testFps} fps`].filter(Boolean).join(' · ')}
								</p>
							{/if}
						</div>
					{/if}
				</form>

				<div class="mt-4 border-t border-gray-800 pt-4">
					{#if confirmDeleteStream}
						<div class="flex items-center justify-between rounded-lg border border-red-800 bg-red-950/50 p-3">
							<p class="text-sm text-gray-300">
								Delete <strong class="text-white">{stream.name}</strong>? All capture plans, captures, timelapses and schedules are permanently removed.
							</p>
							<div class="flex shrink-0 gap-2">
								<button onclick={() => { confirmDeleteStream = false; }} class="rounded px-3 py-1 text-xs font-medium text-gray-400 hover:text-gray-200">Cancel</button>
								<button onclick={handleDeleteStream} disabled={deletingStream} class="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50">{deletingStream ? 'Deleting...' : 'Delete'}</button>
							</div>
						</div>
					{:else}
						<button
							onclick={() => { confirmDeleteStream = true; }}
							class="text-sm font-medium text-red-400 hover:text-red-300"
						>
							Delete camera
						</button>
					{/if}
					<p class="mt-3 text-xs text-gray-600">
						Added {formatDateTime(stream.created_at)} · Updated {timeAgo(stream.updated_at)}
					</p>
				</div>
			</div>
		</div>

		{#if printerBound}
			<CameraPrints streamId={id} refreshKey={diagnosticKey} />
		{/if}

		<!-- Capture plans -->
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
			<div class="mb-4 flex items-center justify-between">
				<h2 class="text-lg font-semibold text-gray-100">
					{printerBound ? 'Other capture plans' : 'Capture plans'}
				</h2>
				<button
					onclick={openPlanWizard}
					class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
				>
					Add capture plan
				</button>
			</div>

			{#if editingProfile}
				<div class="mb-4 rounded-lg border border-blue-700 bg-gray-800 p-4">
					<div class="mb-3 flex items-center justify-between">
						<h3 class="text-sm font-semibold text-gray-200">Edit capture plan</h3>
						<button onclick={() => { editingProfile = null; }} class="text-xs text-gray-400 hover:text-gray-200">Cancel</button>
					</div>
					{#key editingProfile.id}
						<ProfileForm profile={editingProfile} streamId={id} onsubmit={handleUpdateProfile} />
					{/key}
				</div>
			{/if}

			{#if confirmDelete}
				<div class="mb-4 flex items-center justify-between rounded-lg border border-red-800 bg-red-950/50 p-3">
					<p class="text-sm text-gray-300">
						{replaceMode ? 'Replace' : 'Delete'} <strong class="text-white">{confirmDelete.name}</strong>? All captures, timelapses, and schedules will be permanently removed.
					</p>
					<div class="flex shrink-0 gap-2">
						<button onclick={() => { confirmDelete = null; replaceMode = false; }} class="rounded px-3 py-1 text-xs font-medium text-gray-400 hover:text-gray-200">Cancel</button>
						<button onclick={handleDeleteProfile} disabled={profileLoading} class="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50">Delete</button>
					</div>
				</div>
			{/if}

			{#if profiles.length === 0}
				<p class="text-sm text-gray-500">No capture plans yet. Add one to start capturing.</p>
			{:else}
				<div class="space-y-2">
					{#each profiles as profile}
						<div class="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 p-3">
							<div class="flex items-center gap-3">
								<span class="text-sm font-medium text-gray-200">{profile.name}</span>
								<span class="text-xs text-gray-500">every {formatInterval(profile.interval_seconds)}</span>
								{#if profile.resolution_width && profile.resolution_height}
									<span class="text-xs text-gray-500">{profile.resolution_width}x{profile.resolution_height}</span>
								{/if}
								<span class="text-xs text-gray-500">Q{profile.quality}</span>
								{#if profile.hdr_enabled}
									<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
								{/if}
								{#if profile.weather_enabled}
									<span class="rounded bg-cyan-900 px-1.5 py-0.5 text-xs font-medium text-cyan-300">Weather</span>
								{/if}
								{#if haSensorsOf(profile).length}
									<span class="rounded bg-blue-900 px-1.5 py-0.5 text-xs font-medium text-blue-300" title={haSensorsOf(profile).map((s) => s.label).join(', ')}>HA</span>
								{/if}
								{#if profile.auto_disabled}
									<span class="rounded bg-orange-900 px-1.5 py-0.5 text-xs font-medium text-orange-300" title="Automatically disabled due to camera health issues">Auto</span>
								{/if}
							</div>
							<div class="flex items-center gap-2">
								<button
									onclick={() => toggleProfile(profile)}
									class="rounded px-3 py-1 text-xs font-medium transition-colors {profile.enabled ? 'bg-green-900 text-green-300 hover:bg-green-800' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}"
								>
									{profile.enabled ? 'Enabled' : 'Disabled'}
								</button>
								<div class="relative">
									<button
										onclick={(e: MouseEvent) => { e.stopPropagation(); activeMenu = activeMenu === profile.id ? null : profile.id; }}
										class="rounded p-1 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
									>
										<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
											<path d="M10 6a2 2 0 110-4 2 2 0 010 4zm0 6a2 2 0 110-4 2 2 0 010 4zm0 6a2 2 0 110-4 2 2 0 010 4z" />
										</svg>
									</button>
									{#if activeMenu === profile.id}
										<!-- svelte-ignore a11y_no_static_element_interactions -->
										<div class="fixed inset-0 z-10" onclick={() => { activeMenu = null; }}></div>
										<div class="absolute right-0 z-20 mt-1 w-36 rounded-lg border border-gray-700 bg-gray-800 py-1 shadow-lg">
											<button
												onclick={() => { editingProfile = profile; confirmDelete = null; activeMenu = null; }}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Edit</button>
											<button
												onclick={() => { handleDuplicateProfile(profile); }}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Duplicate</button>
											<button
												onclick={() => openRenderWizard(profile)}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Add render schedule</button>
											<button
												onclick={() => { confirmDelete = profile; replaceMode = true; editingProfile = null; activeMenu = null; }}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Replace</button>
											<button
												onclick={() => { confirmDelete = profile; replaceMode = false; editingProfile = null; activeMenu = null; }}
												class="block w-full px-3 py-1.5 text-left text-sm text-red-400 hover:bg-gray-700"
											>Delete</button>
										</div>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		{#if !printerBound || profiles.length > 0}
			<CameraRenderSchedules
				{profiles}
				refreshKey={scheduleKey}
				onadd={openRenderWizardForCamera}
			/>
		{/if}

		<!-- Recent Captures -->
		{#if captures.length > 0}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<h2 class="mb-3 text-lg font-semibold text-gray-100">Recent Captures</h2>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
					{#each captures as capture, i}
						<button
							type="button"
							onclick={() => { previewIndex = i; previewOpen = true; }}
							class="relative aspect-video overflow-hidden rounded-lg bg-gray-800 ring-blue-500 transition hover:ring-2 focus:outline-none focus-visible:ring-2"
							aria-label="Preview capture {i + 1}"
						>
							<img
								src={api.getCaptureImageUrl(capture.id)}
								alt="Capture {capture.id}"
								class="h-full w-full object-cover"
								loading="lazy"
							/>
							{#if capture.weather_temp != null}
								<div class="absolute bottom-0 right-0 rounded-tl bg-black/70 px-1.5 py-0.5 text-[10px] text-gray-200">
									{capture.weather_temp.toFixed(1)}°C
								</div>
							{/if}
						</button>
					{/each}
				</div>
			</div>
		{/if}

		{#if renderWizardDraft}
			<RenderWizard
				draft={renderWizardDraft}
				planFixed={renderWizardPlanFixed}
				lockMode="repeat"
				allowedProfileIds={profiles.map((p) => p.id)}
				onclose={() => { renderWizardDraft = null; }}
				ondone={() => { diagnosticKey++; scheduleKey++; }}
			/>
		{/if}

		{#if showPlanWizard}
			<AddCapturePlanWizard
				streamId={id}
				cameraName={stream.name}
				onclose={() => { showPlanWizard = false; }}
				oncreated={reloadPlans}
			/>
		{/if}

		{#if previewOpen}
			<CapturePreview
				{captures}
				bind:index={previewIndex}
				allLoaded={allCapturesLoaded}
				onLoadMore={loadMoreCaptures}
				onClose={() => (previewOpen = false)}
			/>
		{/if}
	</div>
{/if}
