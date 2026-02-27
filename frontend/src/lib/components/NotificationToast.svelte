<script lang="ts">
	interface Toast {
		id: number;
		title: string;
		body: string;
		level: string;
	}

	interface Props {
		toasts: Toast[];
		onDismiss: (id: number) => void;
	}

	let { toasts, onDismiss }: Props = $props();

	function levelClasses(level: string): string {
		if (level === 'error') return 'border-red-700 bg-red-950';
		if (level === 'warning') return 'border-yellow-700 bg-yellow-950';
		return 'border-blue-700 bg-blue-950';
	}

	function levelTextClass(level: string): string {
		if (level === 'error') return 'text-red-300';
		if (level === 'warning') return 'text-yellow-300';
		return 'text-blue-300';
	}
</script>

<div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
	{#each toasts as toast (toast.id)}
		<div class="w-80 rounded-lg border p-3 shadow-lg {levelClasses(toast.level)}">
			<div class="flex items-start justify-between">
				<div>
					<p class="text-sm font-medium {levelTextClass(toast.level)}">{toast.title}</p>
					<p class="mt-0.5 text-xs text-gray-400">{toast.body}</p>
				</div>
				<button
					onclick={() => onDismiss(toast.id)}
					class="ml-2 text-gray-500 hover:text-gray-300"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
	{/each}
</div>
