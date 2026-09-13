import type { ProfileCreate, ProfileTemplate } from './types';

/**
 * A capture plan being composed, before it exists.
 *
 * Either a plan preset is selected (`presetId`) or the plan is custom
 * (`custom`), never both. The remaining fields map straight onto ProfileCreate,
 * so the custom path needs no translation layer.
 *
 * Shared by the add-camera wizard and the standalone add-plan flow, which is
 * what keeps the guided route and the later route from drifting apart — the
 * same argument that drove RenderOptionsValue.
 */
export interface CapturePlanDraft {
	presetId: number | null;
	custom: boolean;
	name: string;
	interval_seconds: number;
	resolution_width: number | null;
	resolution_height: number | null;
	quality: number;
}

/** Interval choices offered as chips. Anything else is set on the camera later. */
export const PLAN_INTERVALS = [10, 30, 60, 300, 900, 3600];

export const PLAN_RESOLUTIONS: { label: string; dims: [number, number] | null }[] = [
	{ label: 'Source resolution', dims: null },
	{ label: '720p', dims: [1280, 720] },
	{ label: '1080p', dims: [1920, 1080] },
	{ label: '4K', dims: [3840, 2160] }
];

export function defaultCapturePlanDraft(name = ''): CapturePlanDraft {
	return {
		presetId: null,
		custom: false,
		name,
		interval_seconds: 300,
		resolution_width: null,
		resolution_height: null,
		quality: 85
	};
}

/** Enough has been chosen to create something. */
export function capturePlanComplete(draft: CapturePlanDraft): boolean {
	return draft.custom ? draft.name.trim().length > 0 : draft.presetId !== null;
}

/**
 * The interval that will actually apply — the preset's when one is selected,
 * the draft's own when custom. Drives the estimate, which is the whole reason
 * a preset is selected rather than applied on click.
 */
export function effectiveInterval(
	draft: CapturePlanDraft,
	presets: ProfileTemplate[]
): number {
	if (draft.custom) return draft.interval_seconds;
	const preset = presets.find((p) => p.id === draft.presetId);
	return preset?.interval_seconds ?? 0;
}

/** Output dimensions that will apply, or null for the source's own. */
export function effectiveDimensions(
	draft: CapturePlanDraft,
	presets: ProfileTemplate[]
): { w: number; h: number } | null {
	if (draft.custom) {
		return draft.resolution_width && draft.resolution_height
			? { w: draft.resolution_width, h: draft.resolution_height }
			: null;
	}
	const preset = presets.find((p) => p.id === draft.presetId);
	if (preset?.resolution_width && preset?.resolution_height) {
		return { w: preset.resolution_width, h: preset.resolution_height };
	}
	return null;
}

/** The custom path's request body. Preset plans go through applyProfileTemplate. */
export function capturePlanPayload(draft: CapturePlanDraft): ProfileCreate {
	return {
		name: draft.name,
		interval_seconds: draft.interval_seconds,
		resolution_width: draft.resolution_width,
		resolution_height: draft.resolution_height,
		quality: draft.quality
	};
}
