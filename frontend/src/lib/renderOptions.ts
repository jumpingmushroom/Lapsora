import type { Profile, RenderOptionsValue, TimelapseSchedule } from './types';

/**
 * Defaults for a fresh render. These mirror the backend's own defaults on
 * TimelapseGenerate / TimelapseScheduleCreate — notably `mp4`, which the
 * generate dialog used to override with `mkv` for no stated reason.
 */
export function defaultRenderOptions(): RenderOptionsValue {
	return {
		fps: 24,
		fps_mode: 'fixed',
		render_target_seconds: 20,
		format: 'mp4',
		deflicker: 'medium',
		motion_blur: 'off',
		codec: 'auto',
		output_width: null,
		output_height: null,
		quality_preset: 'medium',
		timestamp_overlay: false,
		weather_overlay: false,
		weather_position: 'bottom-right',
		weather_font_size: 24,
		weather_unit: 'C',
		weather_style: 'glass',
		ha_overlay: false,
		ha_overlay_position: 'top-left',
		heatmap_overlay: false,
		heatmap_mode: 'cumulative',
		heatmap_colormap: 'jet',
		heatmap_threshold: 10,
		logo_overlay: false,
		logo_position: 'bottom-right',
		logo_size: 0.12,
		logo_opacity: 0.8
	};
}

/**
 * Seed render settings from a capture plan's own render defaults.
 *
 * A plan carries fps_mode / render_target_seconds / render_fps / render_format,
 * copied from the plan preset it was created from. Before this existed nothing
 * read them, so configuring "target duration, 20s, MP4" on a preset silently
 * did nothing.
 */
export function renderOptionsForProfile(profile: Profile | undefined): RenderOptionsValue {
	const opts = defaultRenderOptions();
	if (!profile) return opts;
	return {
		...opts,
		fps: profile.render_fps ?? opts.fps,
		fps_mode: profile.fps_mode ?? opts.fps_mode,
		render_target_seconds: profile.render_target_seconds ?? opts.render_target_seconds,
		format: profile.render_format ?? opts.format
	};
}

/** Read an existing schedule's stored settings back into the form. */
export function renderOptionsFromSchedule(schedule: TimelapseSchedule): RenderOptionsValue {
	const opts = defaultRenderOptions();
	return {
		fps: schedule.fps ?? opts.fps,
		fps_mode: schedule.fps_mode ?? opts.fps_mode,
		render_target_seconds: schedule.render_target_seconds ?? opts.render_target_seconds,
		format: schedule.format ?? opts.format,
		deflicker: schedule.deflicker ?? opts.deflicker,
		motion_blur: schedule.motion_blur ?? opts.motion_blur,
		codec: schedule.codec ?? opts.codec,
		output_width: schedule.output_width ?? null,
		output_height: schedule.output_height ?? null,
		quality_preset: schedule.quality_preset ?? opts.quality_preset,
		timestamp_overlay: schedule.timestamp_overlay ?? opts.timestamp_overlay,
		weather_overlay: schedule.weather_overlay ?? opts.weather_overlay,
		weather_position: schedule.weather_position ?? opts.weather_position,
		weather_font_size: schedule.weather_font_size ?? opts.weather_font_size,
		weather_unit: schedule.weather_unit ?? opts.weather_unit,
		weather_style: schedule.weather_style ?? opts.weather_style,
		ha_overlay: schedule.ha_overlay ?? opts.ha_overlay,
		ha_overlay_position: schedule.ha_overlay_position ?? opts.ha_overlay_position,
		heatmap_overlay: schedule.heatmap_overlay ?? opts.heatmap_overlay,
		heatmap_mode: schedule.heatmap_mode ?? opts.heatmap_mode,
		heatmap_colormap: schedule.heatmap_colormap ?? opts.heatmap_colormap,
		heatmap_threshold: schedule.heatmap_threshold ?? opts.heatmap_threshold,
		logo_overlay: schedule.logo_overlay ?? opts.logo_overlay,
		logo_position: schedule.logo_position ?? opts.logo_position,
		logo_size: schedule.logo_size ?? opts.logo_size,
		logo_opacity: schedule.logo_opacity ?? opts.logo_opacity
	};
}

/**
 * Drop the settings the chosen format cannot use, so a GIF render doesn't
 * carry a codec and a quality preset the encoder will ignore.
 */
export function renderOptionsPayload(v: RenderOptionsValue): Record<string, unknown> {
	const isGif = v.format === 'gif';
	const supportsCodec = v.format === 'mp4' || v.format === 'mkv';
	return {
		fps: v.fps,
		fps_mode: v.fps_mode,
		render_target_seconds: v.render_target_seconds,
		format: v.format,
		deflicker: v.deflicker,
		motion_blur: isGif ? undefined : v.motion_blur,
		codec: supportsCodec ? v.codec : undefined,
		output_width: isGif ? undefined : (v.output_width || undefined),
		output_height: isGif ? undefined : (v.output_height || undefined),
		quality_preset: isGif ? undefined : v.quality_preset,
		timestamp_overlay: v.timestamp_overlay,
		weather_overlay: v.weather_overlay,
		weather_position: v.weather_overlay ? v.weather_position : undefined,
		weather_font_size: v.weather_overlay ? v.weather_font_size : undefined,
		weather_unit: v.weather_overlay ? v.weather_unit : undefined,
		weather_style: v.weather_overlay ? v.weather_style : undefined,
		ha_overlay: v.ha_overlay,
		ha_overlay_position: v.ha_overlay ? v.ha_overlay_position : undefined,
		heatmap_overlay: v.heatmap_overlay,
		heatmap_mode: v.heatmap_overlay ? v.heatmap_mode : undefined,
		heatmap_colormap: v.heatmap_overlay ? v.heatmap_colormap : undefined,
		heatmap_threshold: v.heatmap_overlay ? v.heatmap_threshold : undefined,
		logo_overlay: v.logo_overlay,
		logo_position: v.logo_overlay ? v.logo_position : undefined,
		logo_size: v.logo_overlay ? v.logo_size : undefined,
		logo_opacity: v.logo_overlay ? v.logo_opacity : undefined
	};
}
