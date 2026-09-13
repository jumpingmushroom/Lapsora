import { describe, it, expect } from 'vitest';
import {
	activeSecondsPerDay,
	sunWindowSeconds,
	framesPerDay,
	scaleFrameSize,
	bytesPerMonth,
	daysUntilFull,
	renderEstimate,
	formatRenderLength,
	SECONDS_PER_DAY,
	FPS_MIN,
	FPS_MAX
} from './estimates';

describe('activeSecondsPerDay', () => {
	it('treats "always" as the whole day', () => {
		expect(activeSecondsPerDay('always', null, null)).toEqual({
			seconds: SECONDS_PER_DAY,
			approximate: false
		});
	});

	it('measures a normal manual window', () => {
		expect(activeSecondsPerDay('manual', '06:00', '20:00')?.seconds).toBe(14 * 3600);
	});

	it('wraps a manual window that spans midnight', () => {
		// 22:00-04:00 is six hours, matching how the capture scheduler reads it.
		expect(activeSecondsPerDay('manual', '22:00', '04:00')?.seconds).toBe(6 * 3600);
	});

	it('returns null for an unparseable window rather than guessing', () => {
		expect(activeSecondsPerDay('manual', '', '20:00')).toBeNull();
		expect(activeSecondsPerDay('manual', '6pm', '20:00')).toBeNull();
		expect(activeSecondsPerDay('manual', '25:00', '20:00')).toBeNull();
	});

	it('marks sun mode approximate and says why', () => {
		const w = activeSecondsPerDay('sun', null, null, ['daylight']);
		expect(w?.approximate).toBe(true);
		expect(w?.caveat).toMatch(/varies by season/);
	});

	it('returns null when sun mode has no events selected', () => {
		expect(activeSecondsPerDay('sun', null, null, [])).toBeNull();
	});
});

describe('sunWindowSeconds', () => {
	it('does not double-count golden hour inside daylight', () => {
		const daylight = sunWindowSeconds(['daylight']);
		expect(sunWindowSeconds(['daylight', 'golden_hour'])).toBe(daylight);
	});

	it('counts golden hour when daylight is not selected', () => {
		expect(sunWindowSeconds(['golden_hour'])).toBeGreaterThan(0);
		expect(sunWindowSeconds(['golden_hour'])).toBeLessThan(sunWindowSeconds(['daylight']));
	});

	it('adds blue hour, which sits outside both daylight and night', () => {
		expect(sunWindowSeconds(['daylight', 'blue_hour'])).toBeGreaterThan(
			sunWindowSeconds(['daylight'])
		);
	});

	it('never exceeds a day', () => {
		const all = sunWindowSeconds(['daylight', 'night', 'golden_hour', 'blue_hour']);
		expect(all).toBeLessThanOrEqual(SECONDS_PER_DAY);
	});
});

describe('framesPerDay', () => {
	it('divides the active window by the interval', () => {
		expect(framesPerDay(SECONDS_PER_DAY, 300)).toBe(288);
		expect(framesPerDay(14 * 3600, 60)).toBe(840);
	});

	it('guards a zero or negative interval', () => {
		expect(framesPerDay(SECONDS_PER_DAY, 0)).toBe(0);
		expect(framesPerDay(SECONDS_PER_DAY, -5)).toBe(0);
	});
});

describe('scaleFrameSize', () => {
	it('scales by pixel count', () => {
		// 1080p -> 720p is 4/9 of the pixels.
		expect(scaleFrameSize(900_000, 1920, 1080, 1280, 720)).toBe(400_000);
	});

	it('returns the sample unchanged when either size is unknown', () => {
		expect(scaleFrameSize(500, null, null, 1280, 720)).toBe(500);
		expect(scaleFrameSize(500, 1920, 1080, null, null)).toBe(500);
	});
});

describe('storage projections', () => {
	it('projects a month at 30 days', () => {
		expect(bytesPerMonth(288, 500_000)).toBe(288 * 500_000 * 30);
	});

	it('reports days until a disk fills', () => {
		expect(daysUntilFull(100, 1_000_000, 1_000_000_000)).toBe(10);
	});

	it('returns null when nothing is being written', () => {
		expect(daysUntilFull(0, 500_000, 1_000)).toBeNull();
		expect(daysUntilFull(100, 0, 1_000)).toBeNull();
	});
});

describe('renderEstimate', () => {
	it('uses the given fps in fixed mode', () => {
		expect(renderEstimate(1440, 'fixed', 24, 20)).toEqual({ fps: 24, durationSeconds: 60 });
	});

	it('derives fps from the frame count in target-duration mode', () => {
		// 400 frames over a 20s target -> 20fps, matching _resolve_fps.
		expect(renderEstimate(400, 'target_duration', 24, 20)?.fps).toBe(20);
	});

	it('clamps exactly as the backend does', () => {
		expect(renderEstimate(10, 'target_duration', 24, 20)?.fps).toBe(FPS_MIN);
		expect(renderEstimate(100000, 'target_duration', 24, 20)?.fps).toBe(FPS_MAX);
	});

	it('falls back to fps when the target is zero', () => {
		expect(renderEstimate(400, 'target_duration', 24, 0)?.fps).toBe(24);
	});

	it('returns null with no frames, so callers show nothing', () => {
		expect(renderEstimate(0, 'fixed', 24, 20)).toBeNull();
	});
});

describe('formatRenderLength', () => {
	it('stays in seconds under a minute', () => {
		expect(formatRenderLength(8.2)).toBe('8s');
	});
	it('splits minutes and seconds', () => {
		expect(formatRenderLength(72)).toBe('1m 12s');
	});
	it('omits a zero seconds part', () => {
		expect(formatRenderLength(120)).toBe('2m');
	});
});
