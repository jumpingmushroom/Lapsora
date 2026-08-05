import { describe, it, expect } from 'vitest';
import {
	formatBytes,
	formatDuration,
	formatCronTime,
	formatInterval,
	formatFinishedAt,
	localToUtcNaive,
	setUse24h
} from './utils';

describe('formatBytes', () => {
	it('handles zero and null distinctly', () => {
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(null)).toBe('--');
	});
	it('scales to KB/MB/GB', () => {
		expect(formatBytes(1024)).toBe('1.0 KB');
		expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
		expect(formatBytes(1024 ** 3)).toBe('1.0 GB');
	});
});

describe('formatDuration', () => {
	it('formats seconds, minutes, hours', () => {
		expect(formatDuration(45)).toBe('45s');
		expect(formatDuration(90)).toBe('1m 30s');
		expect(formatDuration(3700)).toBe('1h 1m');
		expect(formatDuration(null)).toBe('--');
	});
});

describe('formatInterval', () => {
	it('picks the largest sensible unit', () => {
		expect(formatInterval(30)).toBe('30s');
		expect(formatInterval(120)).toBe('2m');
		expect(formatInterval(3600)).toBe('1h');
	});
});

describe('formatCronTime', () => {
	it('renders 24h when enabled', () => {
		setUse24h(true);
		expect(formatCronTime(9, 5)).toBe('09:05');
		expect(formatCronTime(13, 0)).toBe('13:00');
	});
	it('renders 12h with AM/PM when disabled', () => {
		setUse24h(false);
		expect(formatCronTime(13, 0)).toBe('1:00 PM');
		expect(formatCronTime(0, 30)).toBe('12:30 AM');
	});
});

describe('localToUtcNaive', () => {
	it('returns empty for invalid input', () => {
		expect(localToUtcNaive('', '08:00')).toBe('');
		expect(localToUtcNaive('not-a-date', 'nope')).toBe('');
	});
	it('produces a 19-char naive datetime', () => {
		const out = localToUtcNaive('2026-06-12', '08:30');
		expect(out).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
	});
	it('round-trips local -> UTC -> local (TZ-independent)', () => {
		// Interpreting the UTC output back as an instant and reading it in local
		// time must recover the original local wall-clock, regardless of the
		// runner's timezone. This is what guarantees the right frames are picked.
		const out = localToUtcNaive('2026-06-12', '08:30');
		const back = new Date(out + 'Z');
		expect(back.getHours()).toBe(8);
		expect(back.getMinutes()).toBe(30);
	});
});

describe('formatFinishedAt', () => {
	it('returns an em dash when the print has not finished', () => {
		expect(formatFinishedAt('2026-08-05T14:32:00Z', null)).toBe('—');
	});

	it('shows time only when the finish is the same local day as the start', () => {
		// Constructed in local time (month is 0-indexed, so 7 = August) so the
		// "same local day" property holds by construction at any host offset —
		// no fixed UTC pair can guarantee this at every zone.
		const start = new Date(2026, 7, 5, 14, 32);
		const end = new Date(2026, 7, 5, 17, 8);
		const got = formatFinishedAt(start.toISOString(), end.toISOString());
		// Date is already in the Started column, so it is not repeated here.
		expect(got).not.toContain('2026');
		expect(got).toMatch(/\d{1,2}[:.]\d{2}/);
	});

	it('shows the full date-time when the print crosses midnight', () => {
		// Constructed in local time so the "different local day" property holds
		// by construction at any host offset.
		const start = new Date(2026, 7, 5, 22, 10);
		const end = new Date(2026, 7, 6, 4, 32);
		const got = formatFinishedAt(start.toISOString(), end.toISOString());
		expect(got).toContain('2026');
	});
});
