<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream, Profile } from '$lib/types';

	interface StreamWithProfiles {
		stream: Stream;
		profiles: Profile[];
	}

	let groups = $state<StreamWithProfiles[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expandedProfile = $state<number | null>(null);
	let captures = $state<Record<number, { id: number; url: string }[]>>({});

	$effect(() => {
		api.getStreams()
			.then(async (streams) => {
				const results: StreamWithProfiles[] = [];
				await Promise.all(
					streams.map(async (stream) => {
						try {
							const profiles = await api.getStreamProfiles(stream.id);
							results.push({ stream, profiles });
						} catch {
							results.push({ stream, profiles: [] });
						}
					})
				);
				results.sort((a, b) => a.stream.name.localeCompare(b.stream.name));
				groups = results;
			})
			.catch((err) => { error = err instanceof Error ? err.message : 'Failed to load'; })
			.finally(() => { loading = false; });
	});

	async function toggleProfile(profile: Profile) {
		try {
			if (profile.enabled) {
				await api.disableProfile(profile.id);
			} else {
				await api.enableProfile(profile.id);
			}
			// Refresh the profile in-place
			const updated = await api.getProfile(profile.id);
			groups = groups.map((g) => ({
				...g,
				profiles: g.profiles.map((p) => (p.id === updated.id ? updated : p))
			}));
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to toggle');
		}
	}

	async function toggleExpand(profileId: number) {
		if (expandedProfile === profileId) {
			expandedProfile = null;
			return;
		}
		expandedProfile = profileId;
		if (!captures[profileId]) {
			try {
				const caps = await api.getProfileCaptures(profileId, 8);
				captures = { ...captures, [profileId]: caps.map((c) => ({ id: c.id, url: api.getCaptureImageUrl(c.id) })) };
			} catch {
				captures = { ...captures, [profileId]: [] };
			}
		}
	}

	function formatInterval(seconds: number): string {
		if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)}h`;
		if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
		return `${seconds}s`;
	}
</script>

<div class="space-y-6">
	<h1 class="text-3xl font-bold text-white">Profiles</h1>

	{#if loading}
		<p class="text-gray-400">Loading profiles...</p>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
			<p class="text-sm text-red-400">{error}</p>
		</div>
	{:else if groups.length === 0}
		<p class="text-gray-500">No streams configured.</p>
	{:else}
		{#each groups as { stream, profiles }}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-5">
				<div class="mb-3 flex items-center gap-2">
					<a href="/streams/{stream.id}" class="text-lg font-semibold text-gray-100 hover:text-blue-400">{stream.name}</a>
					<span class="text-sm text-gray-500">({profiles.length} profile{profiles.length !== 1 ? 's' : ''})</span>
				</div>

				{#if profiles.length === 0}
					<p class="text-sm text-gray-500">No profiles.</p>
				{:else}
					<div class="space-y-2">
						{#each profiles as profile}
							<div>
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<div
									onclick={() => toggleExpand(profile.id)}
									class="flex w-full items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 p-3 text-left transition-colors hover:border-gray-700"
								>
									<div class="flex flex-wrap items-center gap-2">
										<span class="text-sm font-medium text-gray-200">{profile.name}</span>
										<span class="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">{formatInterval(profile.interval_seconds)}</span>
										{#if profile.resolution_width && profile.resolution_height}
											<span class="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">{profile.resolution_width}x{profile.resolution_height}</span>
										{/if}
										<span class="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">Q{profile.quality}</span>
										{#if profile.hdr_enabled}
											<span class="rounded bg-yellow-900 px-1.5 py-0.5 text-xs font-medium text-yellow-300">HDR</span>
										{/if}
									</div>
									<button
										onclick={(e) => { e.stopPropagation(); toggleProfile(profile); }}
										class="rounded px-3 py-1 text-xs font-medium transition-colors {profile.enabled ? 'bg-green-900 text-green-300 hover:bg-green-800' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}"
									>
										{profile.enabled ? 'Enabled' : 'Disabled'}
									</button>
								</div>

								{#if expandedProfile === profile.id}
									<div class="mt-1 rounded-lg border border-gray-800 bg-gray-800/30 p-3">
										{#if captures[profile.id] && captures[profile.id].length > 0}
											<p class="mb-2 text-xs text-gray-500">Recent captures</p>
											<div class="grid grid-cols-4 gap-2">
												{#each captures[profile.id] as cap}
													<div class="aspect-video overflow-hidden rounded bg-gray-900">
														<img src={cap.url} alt="Capture" class="h-full w-full object-cover" loading="lazy" />
													</div>
												{/each}
											</div>
										{:else}
											<p class="text-sm text-gray-500">No captures yet.</p>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/each}
	{/if}
</div>
