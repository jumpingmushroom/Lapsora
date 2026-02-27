<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import type { Stream, Profile, ProfileCreate, ProfileUpdate, ProfileTemplate, Capture } from '$lib/types';
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

	// Profile actions
	let editingProfile = $state<Profile | null>(null);
	let confirmDelete = $state<Profile | null>(null);
	let activeMenu = $state<number | null>(null);
	let replaceMode = $state(false);

	// Template picker
	let showTemplatePicker = $state(false);
	let templates = $state<ProfileTemplate[]>([]);
	let templateCategory = $state<string | null>(null);
	let templateCategories = $derived([...new Set(templates.map((t) => t.category))].sort());
	let filteredTemplates = $derived(
		templateCategory ? templates.filter((t) => t.category === templateCategory) : templates
	);

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

	async function openTemplatePicker() {
		showTemplatePicker = true;
		showProfileForm = false;
		editingProfile = null;
		if (templates.length === 0) {
			try {
				templates = await api.getProfileTemplates();
			} catch {
				templates = [];
			}
		}
	}

	async function applyTemplate(t: ProfileTemplate) {
		profileLoading = true;
		try {
			await api.applyProfileTemplate(t.id, id);
			profiles = await api.getStreamProfiles(id);
			showTemplatePicker = false;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to apply template');
		} finally {
			profileLoading = false;
		}
	}

	function formatInterval(seconds: number): string {
		if (seconds >= 3600) return `${(seconds / 3600).toFixed(seconds % 3600 === 0 ? 0 : 1)}h`;
		if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
		return `${seconds}s`;
	}

	async function handleUpdateProfile(data: ProfileCreate | ProfileUpdate) {
		if (!editingProfile) return;
		profileLoading = true;
		try {
			await api.updateProfile(editingProfile.id, data as ProfileUpdate);
			profiles = await api.getStreamProfiles(id);
			editingProfile = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update profile');
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
			confirmDelete = null;
			replaceMode = false;
			if (shouldReplace) {
				openTemplatePicker();
			}
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to delete profile');
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
				capture_mode: profile.capture_mode,
				active_start_time: profile.active_start_time,
				active_end_time: profile.active_end_time,
				sun_offset_minutes: profile.sun_offset_minutes
			});
			profiles = await api.getStreamProfiles(id);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to duplicate profile');
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
				<div class="flex gap-2">
					<button
						onclick={openTemplatePicker}
						class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
					>
						{showTemplatePicker ? 'Cancel' : 'From Template'}
					</button>
					<button
						onclick={() => { showProfileForm = !showProfileForm; showTemplatePicker = false; editingProfile = null; }}
						class="rounded-lg border border-gray-600 px-3 py-1.5 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
					>
						{showProfileForm ? 'Cancel' : 'Custom'}
					</button>
				</div>
			</div>

			{#if showTemplatePicker}
				<div class="mb-4 rounded-lg border border-gray-700 bg-gray-800 p-4">
					<div class="mb-3 flex flex-wrap gap-1.5">
						<button
							onclick={() => { templateCategory = null; }}
							class="rounded px-2 py-1 text-xs font-medium transition-colors {templateCategory === null ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:text-gray-200'}"
						>All</button>
						{#each templateCategories as cat}
							<button
								onclick={() => { templateCategory = cat; }}
								class="rounded px-2 py-1 text-xs font-medium transition-colors {templateCategory === cat ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:text-gray-200'}"
							>{cat}</button>
						{/each}
					</div>
					<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
						{#each filteredTemplates as t}
							<button
								onclick={() => applyTemplate(t)}
								disabled={profileLoading}
								class="flex flex-col items-start rounded-lg border border-gray-600 p-3 text-left transition-colors hover:border-blue-500 hover:bg-gray-700 disabled:opacity-50"
							>
								<span class="text-sm font-medium text-gray-100">{t.name}</span>
								{#if t.description}
									<span class="mt-0.5 text-xs text-gray-500">{t.description}</span>
								{/if}
								<div class="mt-1.5 flex flex-wrap gap-1">
									<span class="rounded bg-gray-900 px-1.5 py-0.5 text-xs text-gray-400">{formatInterval(t.interval_seconds)}</span>
									{#if t.resolution_width && t.resolution_height}
										<span class="rounded bg-gray-900 px-1.5 py-0.5 text-xs text-gray-400">{t.resolution_width}x{t.resolution_height}</span>
									{/if}
									<span class="rounded bg-gray-900 px-1.5 py-0.5 text-xs text-gray-400">Q{t.quality}</span>
									{#if t.hdr_enabled}
										<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
									{/if}
								</div>
							</button>
						{/each}
					</div>
					{#if filteredTemplates.length === 0}
						<p class="text-sm text-gray-500">No templates available.</p>
					{/if}
				</div>
			{/if}

			{#if editingProfile}
				<div class="mb-4 rounded-lg border border-blue-700 bg-gray-800 p-4">
					<div class="mb-3 flex items-center justify-between">
						<h3 class="text-sm font-semibold text-gray-200">Edit Profile</h3>
						<button onclick={() => { editingProfile = null; }} class="text-xs text-gray-400 hover:text-gray-200">Cancel</button>
					</div>
					{#key editingProfile.id}
						<ProfileForm profile={editingProfile} onsubmit={handleUpdateProfile} />
					{/key}
				</div>
			{:else if showProfileForm}
				<div class="mb-4 rounded-lg border border-gray-700 bg-gray-800 p-4">
					<ProfileForm onsubmit={handleCreateProfile} />
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
				<p class="text-sm text-gray-500">No profiles yet. Add one to start capturing.</p>
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
												onclick={() => { editingProfile = profile; showProfileForm = false; showTemplatePicker = false; confirmDelete = null; activeMenu = null; }}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Edit</button>
											<button
												onclick={() => { handleDuplicateProfile(profile); }}
												class="block w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-700"
											>Duplicate</button>
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
