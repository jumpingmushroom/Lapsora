let _use24h = false;
export function setUse24h(val: boolean) { _use24h = val; }

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

/**
 * Finish timestamp for the 3D Prints table. Same local day as the start shows
 * only the time — the date is already in the Started column — while a print
 * that crossed midnight shows the full date-time so the span stays unambiguous.
 */
export function formatFinishedAt(startIso: string, finishIso: string | null): string {
	if (!finishIso) return '—';
	const start = new Date(startIso);
	const end = new Date(finishIso);
	if (start.toDateString() === end.toDateString()) {
		return end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: !_use24h });
	}
	return formatDateTime(finishIso);
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

export function timeAgo(iso: string | null): string {
	if (!iso) return 'never';
	const diff = Date.now() - new Date(iso).getTime();
	const mins = Math.floor(diff / 60000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	return `${Math.floor(hrs / 24)}d ago`;
}

/**
 * Convert a local wall-clock date + time (as typed in the UI) to a naive
 * UTC datetime string (YYYY-MM-DDTHH:MM:SS). Captures are stored in UTC, so
 * custom timelapse ranges must be converted from the user's local zone or they
 * select the wrong frames on non-UTC hosts. Returns '' for invalid input.
 */
export function localToUtcNaive(date: string, time: string): string {
	// Validate shape first — the Date parser is lenient and would turn garbage
	// into a plausible-but-wrong instant.
	if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return '';
	const local = new Date(`${date}T${time}:00`);
	if (isNaN(local.getTime())) return '';
	return local.toISOString().slice(0, 19);
}

export function healthDotClass(status: string): string {
	if (status === 'healthy') return 'bg-green-500';
	if (status === 'unhealthy') return 'bg-red-500';
	return 'bg-gray-500';
}
