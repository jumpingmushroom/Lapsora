<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import type { Stream, Profile, ProfileCreate, ProfileUpdate, Capture } from '$lib/types';
	import ProfileForm from '$lib/components/ProfileForm.svelte';

	let id = $derived(Number($page.params.id));

	let stream = $state<Stream | null>(null);
	let profiles = $state<Profile[]>([]);
	let captures = $state<Capture[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Edit form
	let editName = $state('');
	let editEnabled = $state(true);
	let newUrl = $state('');
	let saving = $state(false);
	let saveMsg = $state('');

	// Profile form
	let showProfileForm = $state(false);
	let profileLoading = $state(false);

	// Preview
	let previewKey = $state(0);
	let previewSrc = $derived(`${api.getStreamPreviewUrl(id)}?t=${previewKey}`);

	$effect(() => {
		const currentId = id;
		loading = true;
		error = null;

		Promise.all([
			api.getStream(currentId),
			api.getStreamProfiles(currentId)
		])
			.then(([s, p]) => {
				stream = s;
				editName = s.name;
				editEnabled = s.enabled;
				profiles = p;
				if (p.length > 0) {
					api.getProfileCaptures(p[0].id, 12)
						.then((c) => { captures = c; })
						.catch(() => {});
				}
			})
			.catch((err) => { error = err instanceof Error ? err.message : 'Failed to load'; })
			.finally(() => { loading = false; });
	});

	// Auto-refresh preview every 5 seconds
	$effect(() => {
		const interval = setInterval(() => { previewKey++; }, 5000);
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
			saveMsg = 'Saved';
			setTimeout(() => { saveMsg = ''; }, 2000);
		} catch (err) {
			saveMsg = err instanceof Error ? err.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function handleCreateProfile(data: ProfileCreate | ProfileUpdate) {
		profileLoading = true;
		try {
			await api.createProfile(id, data as ProfileCreate);
			profiles = await api.getStreamProfiles(id);
			showProfileForm = false;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to create profile');
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
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to toggle profile');
		}
	}
</script>

{#if loading}
	<p class="text-gray-400">Loading stream...</p>
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

		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<!-- Live Preview -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<h2 class="mb-3 text-lg font-semibold text-gray-100">Live Preview</h2>
				<div class="aspect-video w-full overflow-hidden rounded-lg bg-black">
					<img
						src={previewSrc}
						alt="{stream.name} live preview"
						class="h-full w-full object-contain"
						onerror={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3'; }}
					/>
				</div>
				<p class="mt-2 text-xs text-gray-500">Auto-refreshes every 5 seconds</p>
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
					<div>
						<label for="edit-url" class="mb-1 block text-sm font-medium text-gray-300">New RTSP URL (leave blank to keep current)</label>
						<input
							id="edit-url"
							type="text"
							bind:value={newUrl}
							placeholder="rtsp://..."
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<label class="flex items-center gap-2">
						<input
							type="checkbox"
							bind:checked={editEnabled}
							class="rounded border-gray-700 bg-gray-800 text-blue-500 focus:ring-blue-500"
						/>
						<span class="text-sm text-gray-300">Enabled</span>
					</label>
					<div class="flex items-center gap-3">
						<button
							type="submit"
							disabled={saving}
							class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
						>
							{saving ? 'Saving...' : 'Save Changes'}
						</button>
						{#if saveMsg}
							<span class="text-sm {saveMsg === 'Saved' ? 'text-green-400' : 'text-red-400'}">{saveMsg}</span>
						{/if}
					</div>
				</form>
			</div>
		</div>

		<!-- Profiles -->
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
			<div class="mb-4 flex items-center justify-between">
				<h2 class="text-lg font-semibold text-gray-100">Profiles</h2>
				<button
					onclick={() => { showProfileForm = !showProfileForm; }}
					class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
				>
					{showProfileForm ? 'Cancel' : 'Add Profile'}
				</button>
			</div>

			{#if showProfileForm}
				<div class="mb-4 rounded-lg border border-gray-700 bg-gray-800 p-4">
					<ProfileForm onsubmit={handleCreateProfile} />
				</div>
			{/if}

			{#if profiles.length === 0}
				<p class="text-sm text-gray-500">No profiles yet. Add one to start capturing.</p>
			{:else}
				<div class="space-y-2">
					{#each profiles as profile}
						<div class="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 p-3">
							<div class="flex items-center gap-3">
								<span class="text-sm font-medium text-gray-200">{profile.name}</span>
								<span class="text-xs text-gray-500">every {profile.interval_seconds}s</span>
								{#if profile.resolution_width && profile.resolution_height}
									<span class="text-xs text-gray-500">{profile.resolution_width}x{profile.resolution_height}</span>
								{/if}
								<span class="text-xs text-gray-500">Q{profile.quality}</span>
								{#if profile.hdr_enabled}
									<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
								{/if}
							</div>
							<button
								onclick={() => toggleProfile(profile)}
								class="rounded px-3 py-1 text-xs font-medium transition-colors {profile.enabled ? 'bg-green-900 text-green-300 hover:bg-green-800' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}"
							>
								{profile.enabled ? 'Enabled' : 'Disabled'}
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Recent Captures -->
		{#if captures.length > 0}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<h2 class="mb-3 text-lg font-semibold text-gray-100">Recent Captures</h2>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
					{#each captures as capture}
						<div class="aspect-video overflow-hidden rounded-lg bg-gray-800">
							<img
								src={api.getCaptureImageUrl(capture.id)}
								alt="Capture {capture.id}"
								class="h-full w-full object-cover"
								loading="lazy"
							/>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}
