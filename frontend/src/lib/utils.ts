let _use24h = false;
export function setUse24h(val: boolean) { _use24h = val; }
export function getUse24h(): boolean { return _use24h; }

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
	return new Date(iso).toLocaleString(undefined, { hour12: !_use24h });
}

export function formatTime(iso: string): string {
	return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: !_use24h });
}

export function formatCronTime(hour: number, minute: number): string {
	if (_use24h) {
		return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
	}
	const period = hour >= 12 ? 'PM' : 'AM';
	const h12 = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
	return `${h12}:${String(minute).padStart(2, '0')} ${period}`;
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
