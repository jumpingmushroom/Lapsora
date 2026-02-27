<script lang="ts">
	import { api } from '$lib/api';
	import type { Notification } from '$lib/types';

	interface Props {
		notifications: Notification[];
		onRefresh: () => void;
	}

	let { notifications, onRefresh }: Props = $props();
	let open = $state(false);

	let unreadCount = $derived(notifications.filter((n) => !n.read).length);

	async function markRead(id: number) {
		await api.markNotificationRead(id);
		onRefresh();
	}

	async function markAllRead() {
		await api.markAllNotificationsRead();
		onRefresh();
	}

	function levelColor(level: string): string {
		if (level === 'error') return 'text-red-400';
		if (level === 'warning') return 'text-yellow-400';
		return 'text-blue-400';
	}

	function timeAgo(iso: string): string {
		const diff = Date.now() - new Date(iso).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		return `${Math.floor(hrs / 24)}d ago`;
	}
</script>

<div class="relative">
	<button
		onclick={() => (open = !open)}
		class="relative rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-800 hover:text-white"
	>
		<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
		</svg>
		{#if unreadCount > 0}
			<span class="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white">
				{unreadCount > 9 ? '9+' : unreadCount}
			</span>
		{/if}
	</button>

	{#if open}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div onclick={() => (open = false)} class="fixed inset-0 z-40"></div>
		<div class="absolute left-0 top-full z-50 mt-2 w-80 rounded-xl border border-gray-700 bg-gray-900 shadow-xl">
			<div class="flex items-center justify-between border-b border-gray-800 px-4 py-3">
				<span class="text-sm font-semibold text-white">Notifications</span>
				{#if unreadCount > 0}
					<button onclick={markAllRead} class="text-xs text-blue-400 hover:text-blue-300">
						Mark all read
					</button>
				{/if}
			</div>
			<div class="max-h-80 overflow-y-auto">
				{#if notifications.length === 0}
					<p class="px-4 py-6 text-center text-sm text-gray-500">No notifications</p>
				{:else}
					{#each notifications.slice(0, 20) as n}
						<button
							onclick={() => { if (!n.read) markRead(n.id); }}
							class="flex w-full flex-col gap-0.5 border-b border-gray-800/50 px-4 py-3 text-left transition-colors hover:bg-gray-800/50 {n.read ? 'opacity-60' : ''}"
						>
							<div class="flex items-center justify-between">
								<span class="text-xs font-medium {levelColor(n.level)}">{n.title}</span>
								<span class="text-[10px] text-gray-500">{timeAgo(n.created_at)}</span>
							</div>
							<span class="text-xs text-gray-400">{n.body}</span>
						</button>
					{/each}
				{/if}
			</div>
		</div>
	{/if}
</div>
