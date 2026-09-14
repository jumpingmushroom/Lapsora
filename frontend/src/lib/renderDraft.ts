import { localToUtcNaive, formatCronTime } from './utils';
import { defaultRenderOptions, renderOptionsFromSchedule } from './renderOptions';
import type { RenderOptionsValue, TimelapseSchedule } from './types';

/**
 * A render being composed — one-shot or recurring.
 *
 * The two used to be separate dialogs that happened to share twenty-four
 * fields. They differ only in *when*: a one-shot render has a time range, a
 * recurring one has a cron expression and a lookback window. Everything else
 * is the same question, so it is the same draft with a branch.
 */
export type RenderMode = 'once' | 'repeat';

export type RangePreset =
	| 'last1h' | 'last24h' | 'today' | 'yesterday'
	| 'last7d' | 'last30d' | 'thisWeek' | 'lastWeek' | 'custom';

export const RANGE_PRESETS: { key: RangePreset; label: string }[] = [
	{ key: 'last1h', label: 'Last 1h' },
	{ key: 'last24h', label: 'Last 24h' },
	{ key: 'today', label: 'Today' },
	{ key: 'yesterday', label: 'Yesterday' },
	{ key: 'last7d', label: 'Last 7d' },
	{ key: 'last30d', label: 'Last 30d' },
	{ key: 'thisWeek', label: 'This week' },
	{ key: 'lastWeek', label: 'Last week' },
	{ key: 'custom', label: 'Custom' }
];

/**
 * Cron and lookback for each recurring preset.
 *
 * These MUST match PRESET_CRONS and PRESET_LOOKBACK in
 * backend/app/routers/timelapse_schedules.py. The backend resolves the cron
 * itself when a preset is sent; these values drive the labels, so a mismatch
 * would describe a schedule as firing at a time it does not.
 */
export const SCHEDULE_PRESETS: Record<string, { label: string; cron: string; lookback: number }> = {
	daily: { label: 'Daily', cron: '5 0 * * *', lookback: 24 },
	weekly: { label: 'Weekly', cron: '30 0 * * 0', lookback: 168 },
	monthly: { label: 'Monthly', cron: '0 1 1 * *', lookback: 730 },
	yearly: { label: 'Yearly', cron: '0 2 1 1 *', lookback: 8760 }
};

export interface RenderDraft {
	profileId: number;
	mode: RenderMode;

	// --- 'once' branch ---
	rangePreset: RangePreset;
	customStartDate: string;
	customStartTime: string;
	customEndDate: string;
	customEndTime: string;

	// --- 'repeat' branch ---
	schedulePreset: string | null;
	cron: string;
	cronCustom: boolean;
	lookbackHours: number | null;
	name: string;

	options: RenderOptionsValue;
}

export function defaultRenderDraft(mode: RenderMode = 'once', profileId = 0): RenderDraft {
	return {
		profileId,
		mode,
		rangePreset: 'last24h',
		customStartDate: '',
		customStartTime: '00:00',
		customEndDate: '',
		customEndTime: '23:59',
		schedulePreset: null,
		cron: '',
		cronCustom: false,
		lookbackHours: null,
		name: '',
		options: defaultRenderOptions()
	};
}

/** Load an existing schedule back into the draft for editing. */
export function renderDraftFromSchedule(schedule: TimelapseSchedule): RenderDraft {
	const known = schedule.preset && SCHEDULE_PRESETS[schedule.preset];
	return {
		...defaultRenderDraft('repeat', schedule.profile_id),
		schedulePreset: known ? schedule.preset : null,
		cron: known ? SCHEDULE_PRESETS[schedule.preset!].cron : schedule.cron_expression,
		cronCustom: !known,
		lookbackHours: schedule.lookback_hours,
		name: schedule.name || '',
		options: renderOptionsFromSchedule(schedule)
	};
}

/**
 * Resolve a range preset to UTC-naive strings.
 *
 * `now` is injectable so this can be tested; production callers omit it.
 * Captures are stored in UTC and these serialize via toISOString(), so the
 * custom branch converts local wall-clock input to UTC too — otherwise a
 * non-UTC user's custom range is shifted by their offset and selects the
 * wrong frames, or none.
 */
export function computePresetRange(
	preset: RangePreset,
	now: Date = new Date()
): { start: string; end: string } | null {
	let start: Date;
	let end: Date = now;

	switch (preset) {
		case 'last1h':
			start = new Date(now.getTime() - 60 * 60 * 1000);
			break;
		case 'last24h':
			start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
			break;
		case 'today':
			start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			break;
		case 'yesterday':
			start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
			end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			break;
		case 'last7d':
			start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
			break;
		case 'last30d':
			start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
			break;
		case 'thisWeek': {
			const day = now.getDay();
			const diff = day === 0 ? 6 : day - 1;
			start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
			break;
		}
		case 'lastWeek': {
			const day = now.getDay();
			const diff = day === 0 ? 6 : day - 1;
			const thisMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - diff);
			start = new Date(thisMonday.getTime() - 7 * 24 * 60 * 60 * 1000);
			end = new Date(thisMonday.getTime() - 1000);
			break;
		}
		case 'custom':
			return null;
	}

	return { start: start.toISOString().slice(0, 19), end: end.toISOString().slice(0, 19) };
}

export function draftRangeStart(draft: RenderDraft, now?: Date): string {
	if (draft.rangePreset === 'custom') {
		if (!draft.customStartDate) return '';
		return localToUtcNaive(draft.customStartDate, draft.customStartTime || '00:00');
	}
	return computePresetRange(draft.rangePreset, now)?.start ?? '';
}

export function draftRangeEnd(draft: RenderDraft, now?: Date): string {
	if (draft.rangePreset === 'custom') {
		if (!draft.customEndDate) return '';
		return localToUtcNaive(draft.customEndDate, draft.customEndTime || '23:59');
	}
	return computePresetRange(draft.rangePreset, now)?.end ?? '';
}

/**
 * Why the draft cannot be submitted yet, or null when it can.
 *
 * A half-filled custom range resolves to '' and would otherwise submit as an
 * unbounded whole-history render; a fully empty one still legitimately means
 * "every frame".
 */
export function renderDraftError(draft: RenderDraft, now?: Date): string | null {
	if (!draft.profileId) return 'Choose a capture plan.';

	if (draft.mode === 'once' && draft.rangePreset === 'custom') {
		const hasStart = draft.customStartDate || draft.customStartTime;
		const hasEnd = draft.customEndDate || draft.customEndTime;
		if (hasStart && !draftRangeStart(draft, now)) return 'Enter a valid start date and time (HH:MM).';
		if (hasEnd && !draftRangeEnd(draft, now)) return 'Enter a valid end date and time (HH:MM).';
	}

	if (draft.mode === 'repeat' && !draft.schedulePreset && !draft.cron.trim()) {
		return 'Choose how often it should run, or enter a cron expression.';
	}

	return null;
}

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/**
 * Describe a schedule from the cron it actually holds.
 *
 * Descriptions used to come from a constant keyed by preset name, so a
 * schedule whose cron had been moved — as an overnight plan's now is — was
 * described by the time it used to fire at. Reading the stored expression
 * means the label cannot disagree with the schedule it names.
 *
 * `periodLabel` comes from the backend and says what the period covers rather
 * than what the preset is called: an overnight plan rendered "daily" covers a
 * night, not a calendar day.
 */
export function describeSchedule(
	cron: string,
	periodLabel?: string | null
): string {
	const parts = cron.trim().split(/\s+/);
	if (parts.length !== 5) return cron;
	const [min, hr, dom, mon, dow] = parts;
	if (!/^\d+$/.test(min) || !/^\d+$/.test(hr)) return cron;
	const at = formatCronTime(Number(hr), Number(min));

	if (dom === '*' && mon === '*' && dow === '*') {
		return periodLabel === 'nightly' ? `Every night, rendered at ${at}` : `Every day at ${at}`;
	}
	if (dom === '*' && mon === '*' && /^\d$/.test(dow)) {
		const day = DAY_NAMES[Number(dow)] ?? `day ${dow}`;
		return periodLabel === 'nightly'
			? `Every week, rendered ${day} at ${at}`
			: `${day} at ${at}`;
	}
	if (/^\d+$/.test(dom) && mon === '*') return `${dom} of each month at ${at}`;
	if (/^\d+$/.test(dom) && /^\d+$/.test(mon)) return `${dom}/${mon} at ${at}`;
	return cron;
}
