<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { defaultCapturePlanDraft, capturePlanComplete, capturePlanPayload } from '$lib/capturePlan';
	import type { CapturePlanDraft } from '$lib/capturePlan';
	import type { Go2rtcStreamInfo, StreamTestResult } from '$lib/types';
	import CapturePlanStep from './CapturePlanStep.svelte';
	import RenderScheduleStep from './RenderScheduleStep.svelte';

	interface Props {
		onclose: () => void;
		/** Opens the single-step "source only" dialog instead. */
		onadvanced: () => void;
	}

	let { onclose, onadvanced }: Props = $props();

	type SourceType = 'rtsp' | 'http_snapshot' | 'http_mjpeg' | 'go2rtc';

	// Described by what the user has, with the protocol as supporting detail —
	// asking someone to classify their camera before naming it is the wrong
	// first question.
	const SOURCES: { value: SourceType; title: string; detail: string }[] = [
		{
			value: 'rtsp',
			title: 'An IP camera with an RTSP URL',
			detail: 'rtsp://… — most network cameras and NVRs'
		},
		{
			value: 'http_snapshot',
			title: 'A snapshot image URL',
			detail: 'A single JPEG endpoint — IP cams, OctoPrint, Frigate'
		},
		{
			value: 'http_mjpeg',
			title: 'A live MJPEG URL',
			detail: 'A multipart stream; one frame is grabbed per capture'
		},
		{
			value: 'go2rtc',
			title: 'Already set up in go2rtc',
			detail: 'RTMP, HLS, WebRTC, ONVIF, Nest, Ring, Tapo…'
		}
	];

	let step = $state(1);

	// --- step 1: source ---
	let name = $state('');
	let sourceType = $state<SourceType>('rtsp');
	let url = $state('');
	let authType = $state<'none' | 'basic' | 'digest' | 'bearer' | 'header'>('none');
	let authUsername = $state('');
	let authSecret = $state('');
	let authHeaderName = $state('');

	let go2rtcStreams = $state<Go2rtcStreamInfo[]>([]);
	let go2rtcLoading = $state(false);
	let go2rtcError = $state('');
	let go2rtcName = $state('');

	let testing = $state(false);
	let testResult = $state<StreamTestResult | null>(null);

	// --- step 2: capture plan ---
	let plan = $state<CapturePlanDraft>(defaultCapturePlanDraft());

	// --- step 3: render ---
	let scheduleChoice = $state('daily');

	// --- finish ---
	let creating = $state(false);
	let createError = $state('');

	let isHttp = $derived(sourceType === 'http_snapshot' || sourceType === 'http_mjpeg');
	let needsUrl = $derived(sourceType !== 'go2rtc');

	let sourceComplete = $derived(
		name.trim().length > 0 && (needsUrl ? url.trim().length > 0 : go2rtcName.length > 0)
	);
	let planComplete = $derived(capturePlanComplete(plan));

	// The test frame doubles as the basis for step 2's storage estimate — it is
	// the only real measurement available before the camera exists.
	let sampleBytes = $derived.by(() => {
		const b64 = testResult?.preview;
		if (!b64) return null;
		const padding = b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0;
		return Math.floor((b64.length * 3) / 4) - padding;
	});

	let sampleDims = $derived.by(() => {
		const res = testResult?.details?.resolution;
		if (typeof res !== 'string') return null;
		const m = /^(\d+)x(\d+)$/.exec(res);
		return m ? { w: Number(m[1]), h: Number(m[2]) } : null;
	});

	function sourcePayload() {
		if (sourceType === 'go2rtc') {
			return { source_type: 'go2rtc' as const, go2rtc_name: go2rtcName };
		}
		return {
			source_type: sourceType,
			url,
			auth_type: authType,
			auth_username: authType === 'basic' || authType === 'digest' ? authUsername : undefined,
			auth_secret: authType !== 'none' ? authSecret : undefined,
			auth_header_name: authType === 'header' ? authHeaderName : undefined
		};
	}

	async function loadGo2rtc() {
		go2rtcLoading = true;
		go2rtcError = '';
		try {
			go2rtcStreams = await api.discoverGo2rtcStreams();
		} catch (err) {
			go2rtcError = err instanceof Error ? err.message : 'Failed to discover streams';
			go2rtcStreams = [];
		} finally {
			go2rtcLoading = false;
		}
	}

	function selectSource(value: SourceType) {
		sourceType = value;
		testResult = null;
		if (value === 'go2rtc' && go2rtcStreams.length === 0) loadGo2rtc();
	}

	async function runTest() {
		testing = true;
		testResult = null;
		try {
			testResult = await api.testSource(sourcePayload());
		} catch (err) {
			testResult = {
				success: false,
				message: err instanceof Error ? err.message : 'Test failed'
			};
		} finally {
			testing = false;
		}
	}

	function goToPlanStep() {
		step = 2;
		if (!plan.name) plan.name = name;
	}

	async function finish() {
		creating = true;
		createError = '';
		let streamId: number | null = null;
		try {
			const stream = await api.createStream({ name, ...sourcePayload() });
			streamId = stream.id;

			const profile = plan.custom
				? await api.createProfile(streamId, capturePlanPayload(plan))
				: await api.applyProfileTemplate(plan.presetId!, streamId, plan.name);
			const profileId = profile.id;

			if (scheduleChoice !== 'none') {
				await api.createTimelapseSchedule({
					profile_id: profileId,
					preset: scheduleChoice,
					name: scheduleChoice === 'daily' ? 'Daily' : 'Weekly'
				});
			}

			goto(`/streams/${streamId}`);
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Something went wrong';
			// There is no transaction across three endpoints. Say plainly what
			// does exist rather than silently deleting the camera, so the user
			// can finish the job instead of starting over.
			createError = streamId
				? `The camera was created, but the rest didn't finish: ${message}. Open the camera to add a capture plan.`
				: `Could not create the camera: ${message}`;
			creating = false;
		}
	}

	const fieldClass =
		'w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
	const labelClass = 'mb-1 block text-sm font-medium text-gray-300';
</script>

<!-- Escape is the keyboard equivalent of the backdrop click below. -->
<svelte:window onkeydown={(e) => { if (e.key === 'Escape') onclose(); }} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
	onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}
>
	<div class="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl bg-gray-900 shadow-xl">
		<!-- Header + step rail -->
		<div class="shrink-0 border-b border-gray-800 p-4">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="text-lg font-semibold text-gray-100">Add camera</h2>
				<button onclick={onclose} aria-label="Close" class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<ol class="flex items-center gap-2 text-xs">
				{#each ['Source', 'Capture plan', 'Render'] as title, i}
					{@const n = i + 1}
					<li class="flex items-center gap-2">
						<span
							class="flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold {
								step > n ? 'bg-green-900 text-green-300'
								: step === n ? 'bg-blue-600 text-white'
								: 'bg-gray-800 text-gray-500'
							}"
						>{step > n ? '✓' : n}</span>
						<span class={step === n ? 'font-medium text-gray-200' : 'text-gray-500'}>{title}</span>
					</li>
					{#if n < 3}
						<li aria-hidden="true" class="h-px w-6 bg-gray-700"></li>
					{/if}
				{/each}
			</ol>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto p-4">
			{#if step === 1}
				<div>
					<label for="wiz-name" class={labelClass}>Name</label>
					<input id="wiz-name" type="text" bind:value={name} placeholder="e.g. Front Yard" class={fieldClass} />
				</div>

				<div>
					<span class={labelClass}>What are you connecting to?</span>
					<div class="space-y-2">
						{#each SOURCES as source}
							<button
								type="button"
								onclick={() => selectSource(source.value)}
								class="flex w-full flex-col items-start rounded-lg border p-3 text-left transition-colors {
									sourceType === source.value
										? 'border-blue-500 bg-blue-950/40'
										: 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
								}"
							>
								<span class="text-sm font-medium text-gray-100">{source.title}</span>
								<span class="mt-0.5 text-xs text-gray-500">{source.detail}</span>
							</button>
						{/each}
					</div>
				</div>

				{#if needsUrl}
					<div>
						<label for="wiz-url" class={labelClass}>
							{sourceType === 'rtsp' ? 'RTSP URL' : sourceType === 'http_mjpeg' ? 'MJPEG stream URL' : 'Snapshot URL'}
						</label>
						<input
							id="wiz-url"
							type="text"
							bind:value={url}
							oninput={() => { testResult = null; }}
							placeholder={sourceType === 'rtsp' ? 'rtsp://…' : sourceType === 'http_mjpeg' ? 'http://…/mjpeg' : 'http://…/snapshot.jpg'}
							class={fieldClass}
						/>
					</div>

					{#if isHttp}
						<div>
							<label for="wiz-auth" class={labelClass}>Authentication</label>
							<select id="wiz-auth" bind:value={authType} class={fieldClass}>
								<option value="none">None</option>
								<option value="basic">Basic</option>
								<option value="digest">Digest</option>
								<option value="bearer">Bearer token</option>
								<option value="header">Custom header</option>
							</select>
						</div>
						{#if authType === 'basic' || authType === 'digest'}
							<div class="grid grid-cols-2 gap-3">
								<div>
									<label for="wiz-user" class={labelClass}>Username</label>
									<input id="wiz-user" type="text" bind:value={authUsername} class={fieldClass} />
								</div>
								<div>
									<label for="wiz-pass" class={labelClass}>Password</label>
									<input id="wiz-pass" type="password" autocomplete="off" bind:value={authSecret} class={fieldClass} />
								</div>
							</div>
						{:else if authType === 'bearer'}
							<div>
								<label for="wiz-token" class={labelClass}>Token</label>
								<input id="wiz-token" type="password" autocomplete="off" bind:value={authSecret} class={fieldClass} />
							</div>
						{:else if authType === 'header'}
							<div class="grid grid-cols-2 gap-3">
								<div>
									<label for="wiz-hname" class={labelClass}>Header name</label>
									<input id="wiz-hname" type="text" bind:value={authHeaderName} placeholder="X-API-Key" class={fieldClass} />
								</div>
								<div>
									<label for="wiz-hval" class={labelClass}>Header value</label>
									<input id="wiz-hval" type="password" autocomplete="off" bind:value={authSecret} class={fieldClass} />
								</div>
							</div>
						{/if}
					{/if}
				{:else}
					<div>
						<label for="wiz-go2rtc" class={labelClass}>go2rtc stream</label>
						{#if go2rtcLoading}
							<p class="text-sm text-gray-400">Loading streams…</p>
						{:else if go2rtcError}
							<p class="text-sm text-red-400">{go2rtcError}</p>
							<a href="/settings" class="mt-1 inline-block text-sm text-blue-400 hover:text-blue-300">Configure go2rtc in Settings</a>
						{:else if go2rtcStreams.length === 0}
							<p class="text-sm text-gray-500">No streams found on the go2rtc server.</p>
						{:else}
							<select
								id="wiz-go2rtc"
								bind:value={go2rtcName}
								onchange={() => { testResult = null; }}
								class={fieldClass}
							>
								<option value="" disabled>Select a stream</option>
								{#each go2rtcStreams as s}
									<option value={s.name}>{s.name}</option>
								{/each}
							</select>
						{/if}
					</div>
				{/if}

				<!-- Test before saving: a typo should fail here, not leave a broken camera behind -->
				<div class="rounded-lg border border-gray-800 bg-gray-800/40 p-3">
					<div class="flex items-center justify-between gap-3">
						<p class="text-xs text-gray-400">Check the source works before adding it.</p>
						<button
							type="button"
							onclick={runTest}
							disabled={testing || (needsUrl ? !url.trim() : !go2rtcName)}
							class="shrink-0 rounded-lg border border-gray-600 px-3 py-1.5 text-sm font-medium text-gray-200 transition-colors hover:bg-gray-700 disabled:opacity-40"
						>
							{testing ? 'Testing…' : 'Test & preview'}
						</button>
					</div>

					{#if testResult}
						<div class="mt-3 space-y-2">
							<p class="text-sm {testResult.success ? 'text-green-400' : 'text-red-400'}">
								{testResult.success ? '✓' : '✕'} {testResult.message}
							</p>
							{#if testResult.details}
								<p class="text-xs text-gray-500">
									{Object.entries(testResult.details).map(([k, v]) => `${k}: ${v}`).join(' · ')}
								</p>
							{/if}
							{#if testResult.preview}
								<img
									src="data:image/jpeg;base64,{testResult.preview}"
									alt="Frame from the camera"
									class="w-full rounded-md border border-gray-700"
								/>
							{:else if testResult.success}
								<p class="text-xs text-gray-500">Connected, but no still frame was available to preview.</p>
							{/if}
						</div>
					{/if}
				</div>
			{:else if step === 2}
				<CapturePlanStep
					bind:value={plan}
					cameraName={name}
					{sampleBytes}
					sampleWidth={sampleDims?.w ?? null}
					sampleHeight={sampleDims?.h ?? null}
					idPrefix="wiz-plan"
				/>
			{:else}
				<RenderScheduleStep bind:value={scheduleChoice} />

				{#if createError}
					<p class="rounded-lg border border-red-800 bg-red-950/50 px-3 py-2 text-sm text-red-300">{createError}</p>
				{/if}
			{/if}
		</div>

		<!-- Footer -->
		<div class="flex shrink-0 items-center justify-between border-t border-gray-800 p-4">
			{#if step === 1}
				<button onclick={onadvanced} class="text-xs text-gray-500 hover:text-gray-300">
					Advanced: add the source only
				</button>
			{:else}
				<button
					onclick={() => { step -= 1; }}
					class="rounded-lg px-3 py-2 text-sm font-medium text-gray-400 hover:text-gray-200"
				>
					Back
				</button>
			{/if}

			<div class="flex gap-2">
				<button onclick={onclose} class="rounded-lg px-4 py-2 text-sm font-medium text-gray-400 hover:text-gray-200">
					Cancel
				</button>
				{#if step === 1}
					<button
						onclick={goToPlanStep}
						disabled={!sourceComplete}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
					>
						Next
					</button>
				{:else if step === 2}
					<button
						onclick={() => { step = 3; }}
						disabled={!planComplete}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
					>
						Next
					</button>
				{:else}
					<button
						onclick={finish}
						disabled={creating}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{creating ? 'Adding…' : 'Add camera'}
					</button>
				{/if}
			</div>
		</div>
	</div>
</div>
