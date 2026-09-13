/**
 * Derived figures for the capture and render forms.
 *
 * These answer the three questions the whole application exists to trade off —
 * how many frames a plan produces, how much disk that costs, and how long the
 * resulting video runs — none of which appeared anywhere before.
 *
 * Everything here is deliberately conservative about what it claims. A figure
 * we cannot ground in real data is not shown at all rather than guessed: see
 * `frameSizeBasis`, which returns null when there is nothing to base it on.
 */

export const SECONDS_PER_DAY = 86400;
const DAYS_PER_MONTH = 30;

// Mirrors FPS_MIN / FPS_MAX in backend/app/services/timelapse.py. If those
// change, the preview here silently stops matching the render.
export const FPS_MIN = 5;
export const FPS_MAX = 60;

export interface ActiveWindow {
	seconds: number;
	/** True when the figure is an annual average rather than an exact window. */
	approximate: boolean;
	/** Shown next to an approximate figure to say why. */
	caveat?: string;
}

function parseHhMm(value: string | null | undefined): number | null {
	if (!value) return null;
	const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
	if (!m) return null;
	const h = Number(m[1]);
	const min = Number(m[2]);
	if (h > 23 || min > 59) return null;
	return h * 3600 + min * 60;
}

/**
 * Rough annual-average durations for the sun windows, in seconds.
 *
 * Averaged over a year, daylight is close to 12h at every latitude. Night is
 * shorter than its mirror because civil twilight sits between the two. Golden
 * hour falls inside daylight, so it only adds time when daylight is not
 * already selected; blue hour is twilight and sits outside both.
 */
const SUN_EVENT_SECONDS = {
	daylight: 12 * 3600,
	night: 10.5 * 3600,
	golden_hour: 1.5 * 3600,
	blue_hour: 1 * 3600
};

export function sunWindowSeconds(events: string[]): number {
	const has = (e: string) => events.includes(e);
	let total = 0;
	if (has('daylight')) total += SUN_EVENT_SECONDS.daylight;
	if (has('night')) total += SUN_EVENT_SECONDS.night;
	if (has('golden_hour') && !has('daylight')) total += SUN_EVENT_SECONDS.golden_hour;
	if (has('blue_hour')) total += SUN_EVENT_SECONDS.blue_hour;
	return Math.min(total, SECONDS_PER_DAY);
}

/** Seconds per day a plan actually captures for. */
export function activeSecondsPerDay(
	captureMode: string,
	activeStart: string | null | undefined,
	activeEnd: string | null | undefined,
	sunEvents: string[] = []
): ActiveWindow | null {
	if (captureMode === 'always') {
		return { seconds: SECONDS_PER_DAY, approximate: false };
	}

	if (captureMode === 'manual') {
		const start = parseHhMm(activeStart);
		const end = parseHhMm(activeEnd);
		if (start === null || end === null) return null;
		// A start after the end means the window spans midnight, exactly as the
		// capture scheduler reads it.
		const seconds = end > start ? end - start : SECONDS_PER_DAY - (start - end);
		return { seconds, approximate: false };
	}

	if (captureMode === 'sun') {
		const seconds = sunWindowSeconds(sunEvents);
		if (seconds === 0) return null;
		return {
			seconds,
			approximate: true,
			caveat: 'annual average — varies by season'
		};
	}

	return null;
}

export function framesPerDay(activeSeconds: number, intervalSeconds: number): number {
	if (intervalSeconds <= 0) return 0;
	return Math.floor(activeSeconds / intervalSeconds);
}

export interface FrameSize {
	bytes: number;
	/** 'measured' from this plan's own frames; 'sampled' from one test frame. */
	basis: 'measured' | 'sampled';
	/** How many frames the measurement averaged over. */
	sampleCount?: number;
}

/**
 * Scale a sample frame's size to a different output resolution.
 *
 * JPEG size tracks pixel count far more closely than it tracks anything else
 * we know here, so that is the only adjustment made. Quality is deliberately
 * not modelled: its effect on size is non-linear and camera-dependent, and a
 * wrong correction would read as precision we do not have.
 */
export function scaleFrameSize(
	sampleBytes: number,
	sampleWidth: number | null,
	sampleHeight: number | null,
	targetWidth: number | null,
	targetHeight: number | null
): number {
	if (!sampleWidth || !sampleHeight || !targetWidth || !targetHeight) return sampleBytes;
	const ratio = (targetWidth * targetHeight) / (sampleWidth * sampleHeight);
	return Math.round(sampleBytes * ratio);
}

export function bytesPerMonth(framesPerDayCount: number, frameBytes: number): number {
	return framesPerDayCount * frameBytes * DAYS_PER_MONTH;
}

/** Days until `freeBytes` runs out at this rate, or null if it never does. */
export function daysUntilFull(
	framesPerDayCount: number,
	frameBytes: number,
	freeBytes: number
): number | null {
	const perDay = framesPerDayCount * frameBytes;
	if (perDay <= 0) return null;
	return Math.floor(freeBytes / perDay);
}

export interface RenderEstimate {
	fps: number;
	durationSeconds: number;
}

/**
 * What a render will actually produce. Mirrors `_resolve_fps` on the backend,
 * including the clamp, so the preview does not promise a length the encoder
 * will not deliver.
 */
export function renderEstimate(
	frameCount: number,
	fpsMode: string,
	fps: number,
	targetSeconds: number
): RenderEstimate | null {
	if (frameCount <= 0) return null;
	let effectiveFps = fps;
	if (fpsMode === 'target_duration' && targetSeconds > 0) {
		effectiveFps = Math.max(FPS_MIN, Math.min(FPS_MAX, Math.round(frameCount / targetSeconds)));
	}
	if (effectiveFps <= 0) return null;
	return { fps: effectiveFps, durationSeconds: frameCount / effectiveFps };
}

/** "1,440 frames" — grouped, because these run to five figures. */
export function formatCount(n: number): string {
	return n.toLocaleString();
}

/** Short duration for render lengths: "8s", "1m 12s". */
export function formatRenderLength(seconds: number): string {
	const rounded = Math.round(seconds);
	if (rounded < 60) return `${rounded}s`;
	const m = Math.floor(rounded / 60);
	const s = rounded % 60;
	return s ? `${m}m ${s}s` : `${m}m`;
}
