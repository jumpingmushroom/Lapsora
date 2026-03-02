export function formatBytes(bytes: number | null): string {
	if (!bytes || bytes === 0) return bytes === 0 ? '0 B' : '--';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`;
}

export function formatDate(iso: string | null): string {
	if (!iso) return 'N/A';
	return new Date(iso).toLocaleDateString();
}

export function formatDateTime(iso: string): string {
	return new Date(iso).toLocaleString();
}

export function formatDuration(seconds: number | null): string {
	if (!seconds) return '--';
	if (seconds < 60) return `${Math.round(seconds)}s`;
	if (seconds < 3600) {
		const m = Math.floor(seconds / 60);
		const s = Math.round(seconds % 60);
		return `${m}m ${s}s`;
	}
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	return `${h}h ${m}m`;
}

export function formatInterval(seconds: number): string {
	if (seconds >= 3600) return `${(seconds / 3600).toFixed(seconds % 3600 === 0 ? 0 : 1)}h`;
	if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
	return `${seconds}s`;
}
