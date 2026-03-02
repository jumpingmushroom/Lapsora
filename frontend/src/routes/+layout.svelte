<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import type { Notification } from '$lib/types';
	import NotificationBell from '$lib/components/NotificationBell.svelte';
	import NotificationToast from '$lib/components/NotificationToast.svelte';

	let { children }: { children: Snippet } = $props();

	let notifications = $state<Notification[]>([]);
	let toasts = $state<{ id: number; title: string; body: string; level: string }[]>([]);
	let toastCounter = $state(0);

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1' },
		{ href: '/streams', label: 'Streams', icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
		{ href: '/profiles', label: 'Templates', icon: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4' },
		{ href: '/timelapses', label: 'Timelapses', icon: 'M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z' },
		{ href: '/files', label: 'Files', icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
		{ href: '/statistics', label: 'Statistics', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
		{ href: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' }
	];

	function loadNotifications() {
		api.getNotifications({ limit: 30 }).then((n) => {
			notifications = n;
		}).catch(() => {});
	}

	function dismissToast(id: number) {
		toasts = toasts.filter((t) => t.id !== id);
	}

	// Load notifications once on mount
	$effect(() => {
		loadNotifications();
	});

	// SSE connection - separate effect so notification changes don't trigger reconnection
	$effect(() => {
		const es = new EventSource(api.getNotificationStreamUrl());
		es.addEventListener('notification', (e) => {
			try {
				const data = JSON.parse(e.data);

				// Progress events are transient — dispatch but don't persist or toast
				if (data.event_type === 'timelapse_progress') {
					window.dispatchEvent(new CustomEvent('lapsora:notification', { detail: data }));
					return;
				}

				const notif: Notification = {
					id: data.id,
					event_type: data.event_type,
					title: data.title,
					body: data.body,
					level: data.level,
					read: false,
					created_at: data.created_at
				};
				notifications = [notif, ...notifications.slice(0, 29)];

				const tid = ++toastCounter;
				toasts = [...toasts, { id: tid, title: data.title, body: data.body, level: data.level }];
				setTimeout(() => {
					toasts = toasts.filter((t) => t.id !== tid);
				}, 5000);

				window.dispatchEvent(new CustomEvent('lapsora:notification', { detail: data }));
			} catch {}
		});

		return () => es.close();
	});
</script>

<div class="flex h-screen bg-gray-950 text-gray-100">
	<aside class="fixed left-0 top-0 z-50 flex h-full w-56 flex-col border-r border-gray-800 bg-gray-900">
		<div class="flex h-14 items-center justify-between border-b border-gray-800 px-4">
			<h1 class="text-lg font-bold tracking-tight text-white">Lapsora</h1>
			<NotificationBell {notifications} onRefresh={loadNotifications} />
		</div>
		<nav class="flex-1 space-y-1 p-3">
			{#each navItems as item}
				<a
					href={item.href}
					class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors {
						$page.url.pathname === item.href || (item.href !== '/' && $page.url.pathname.startsWith(item.href))
							? 'bg-gray-800 text-white font-medium'
							: 'text-gray-400 hover:bg-gray-800 hover:text-white'
					}"
				>
					<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d={item.icon} />
					</svg>
					{item.label}
				</a>
			{/each}
		</nav>
	</aside>

	<main class="ml-56 flex-1 overflow-auto p-6">
		{@render children()}
	</main>
</div>

<NotificationToast {toasts} onDismiss={dismissToast} />
