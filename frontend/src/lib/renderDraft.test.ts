import { describe, it, expect } from 'vitest';
import {
	computePresetRange,
	defaultRenderDraft,
	renderDraftFromSchedule,
	draftRangeStart,
	draftRangeEnd,
	renderDraftError,
	SCHEDULE_PRESETS
} from './renderDraft';
import type { TimelapseSchedule } from './types';

// A fixed Wednesday, so weekday arithmetic is deterministic.
const NOW = new Date(2026, 8, 9, 14, 30, 0); // 2026-09-09, local

describe('computePresetRange', () => {
	it('walks back a fixed span for rolling presets', () => {
		const r = computePresetRange('last24h', NOW)!;
		const spanMs = Date.parse(r.end + 'Z') - Date.parse(r.start + 'Z');
		expect(spanMs).toBe(24 * 60 * 60 * 1000);
	});

	it('starts "today" at local midnight, expressed in UTC', () => {
		const r = computePresetRange('today', NOW)!;
		// The string is UTC; parsing it back must name the same instant as
		// local midnight, whatever zone the runner is in.
		expect(Date.parse(r.start + 'Z')).toBe(new Date(2026, 8, 9).getTime());
	});

	it('bounds "yesterday" at both ends', () => {
		const r = computePresetRange('yesterday', NOW)!;
		const spanMs = Date.parse(r.end + 'Z') - Date.parse(r.start + 'Z');
		expect(spanMs).toBe(24 * 60 * 60 * 1000);
	});

	it('starts the week on Monday', () => {
		// NOW is a Wednesday, so this week began two days earlier.
		const r = computePresetRange('thisWeek', NOW)!;
		const start = new Date(Date.parse(r.start + 'Z'));
		expect(start.getDay()).toBe(1);
	});

	it('makes last week a full seven days ending just before this one', () => {
		const r = computePresetRange('lastWeek', NOW)!;
		const spanMs = Date.parse(r.end + 'Z') - Date.parse(r.start + 'Z');
		// Seven days minus the one second that keeps it off Monday 00:00:00.
		expect(spanMs).toBe(7 * 24 * 60 * 60 * 1000 - 1000);
	});

	it('returns null for custom, which has no computable range', () => {
		expect(computePresetRange('custom', NOW)).toBeNull();
	});
});

describe('draft range resolution', () => {
	it('uses the preset when one is chosen', () => {
		const d = defaultRenderDraft('once', 1);
		expect(draftRangeStart(d, NOW)).not.toBe('');
		expect(draftRangeEnd(d, NOW)).not.toBe('');
	});

	it('is empty for a custom range with nothing filled in', () => {
		const d = { ...defaultRenderDraft('once', 1), rangePreset: 'custom' as const };
		expect(draftRangeStart(d, NOW)).toBe('');
		expect(draftRangeEnd(d, NOW)).toBe('');
	});

	it('converts custom local input to UTC', () => {
		const d = {
			...defaultRenderDraft('once', 1),
			rangePreset: 'custom' as const,
			customStartDate: '2026-09-01',
			customStartTime: '12:00'
		};
		const start = draftRangeStart(d, NOW);
		// Whatever the runner's zone, it must name the same instant as local noon.
		expect(Date.parse(start + 'Z')).toBe(new Date(2026, 8, 1, 12, 0).getTime());
	});
});

describe('renderDraftError', () => {
	it('requires a capture plan', () => {
		const d = defaultRenderDraft('once', 0);
		expect(renderDraftError(d, NOW)).toMatch(/capture plan/i);
	});

	it('allows a fully empty custom range, which means every frame', () => {
		const d = { ...defaultRenderDraft('once', 1), rangePreset: 'custom' as const, customStartTime: '', customEndTime: '' };
		expect(renderDraftError(d, NOW)).toBeNull();
	});

	it('rejects a half-filled custom range rather than rendering all of history', () => {
		const d = {
			...defaultRenderDraft('once', 1),
			rangePreset: 'custom' as const,
			customStartTime: 'nonsense',
			customStartDate: ''
		};
		expect(renderDraftError(d, NOW)).toMatch(/start date/i);
	});

	it('requires a frequency or a cron for a recurring render', () => {
		const d = defaultRenderDraft('repeat', 1);
		expect(renderDraftError(d, NOW)).toMatch(/how often|cron/i);
	});

	it('accepts a recurring render once a preset is chosen', () => {
		const d = { ...defaultRenderDraft('repeat', 1), schedulePreset: 'daily', cron: SCHEDULE_PRESETS.daily.cron };
		expect(renderDraftError(d, NOW)).toBeNull();
	});
});

describe('renderDraftFromSchedule', () => {
	const base = {
		id: 7, profile_id: 3, name: 'Nightly', preset: 'daily',
		cron_expression: '5 0 * * *', fps: 30, fps_mode: 'fixed', render_target_seconds: 20,
		format: 'mkv', deflicker: 'heavy', lookback_hours: 24,
		timestamp_overlay: true, weather_overlay: false, weather_position: 'top-left',
		weather_font_size: 18, weather_unit: 'F', weather_style: 'badge',
		heatmap_overlay: false, heatmap_mode: 'cumulative', heatmap_colormap: 'jet',
		heatmap_threshold: 10, logo_overlay: false, logo_position: 'bottom-right',
		logo_size: 0.2, logo_opacity: 0.5, motion_blur: 'low', codec: 'h265',
		output_width: null, output_height: null, quality_preset: 'high',
		enabled: true, created_at: '', updated_at: '', next_run: null
	} as unknown as TimelapseSchedule;

	it('recognises a known preset and keeps it out of custom-cron mode', () => {
		const d = renderDraftFromSchedule(base);
		expect(d.mode).toBe('repeat');
		expect(d.schedulePreset).toBe('daily');
		expect(d.cronCustom).toBe(false);
	});

	it('treats an unrecognised preset as a custom cron', () => {
		const d = renderDraftFromSchedule({ ...base, preset: null, cron_expression: '*/5 * * * *' });
		expect(d.cronCustom).toBe(true);
		expect(d.cron).toBe('*/5 * * * *');
	});

	it('carries the stored render settings through', () => {
		const d = renderDraftFromSchedule(base);
		expect(d.options.fps).toBe(30);
		expect(d.options.format).toBe('mkv');
		expect(d.options.codec).toBe('h265');
		expect(d.options.logo_size).toBe(0.2);
	});
});
