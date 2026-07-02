export type StreamSourceType = 'rtsp' | 'go2rtc' | 'http_snapshot' | 'http_mjpeg';
export type StreamAuthType = 'none' | 'basic' | 'digest' | 'bearer' | 'header';

export interface Stream {
	id: number;
	name: string;
	source_type: string;
	go2rtc_name: string | null;
	url_masked: string | null;
	auth_type?: string;
	auth_username?: string | null;
	auth_header_name?: string | null;
	has_auth?: boolean;
	enabled: boolean;
	health_status: string;
	consecutive_failures: number;
	last_checked_at: string | null;
	created_at: string;
	updated_at: string;
}

export interface StreamCreate {
	name: string;
	url?: string;
	source_type?: StreamSourceType;
	go2rtc_name?: string;
	auth_type?: StreamAuthType;
	auth_username?: string | null;
	auth_secret?: string | null;
	auth_header_name?: string | null;
}

export interface Go2rtcConfig {
	url: string;
	configured?: boolean;
	connected?: boolean;
}

export interface Go2rtcStreamInfo {
	name: string;
	producers: unknown[];
}

export interface StreamUpdate {
	name?: string;
	url?: string;
	enabled?: boolean;
	auth_type?: StreamAuthType;
	auth_username?: string | null;
	auth_secret?: string | null;
	auth_header_name?: string | null;
}

export interface Profile {
	id: number;
	stream_id: number;
	name: string;
	interval_seconds: number;
	resolution_width: number | null;
	resolution_height: number | null;
	quality: number;
	hdr_enabled: boolean;
	weather_enabled: boolean;
	ha_sensors?: string | null;
	enabled: boolean;
	auto_disabled: boolean;
	capture_mode: string;
	active_start_time: string | null;
	active_end_time: string | null;
	sun_offset_minutes: number;
	sun_events: string;
	ir_only: boolean;
	ir_chroma_threshold: number;
	source_template_id: number | null;
	fps_mode: string;
	render_target_seconds: number;
	render_fps: number;
	render_format: string;
	created_at: string;
	updated_at: string;
}

export interface ProfileTemplate {
	id: number;
	name: string;
	category: string;
	description: string;
	interval_seconds: number;
	resolution_width: number | null;
	resolution_height: number | null;
	quality: number;
	hdr_enabled: boolean;
	fps_mode: string;
	render_target_seconds: number;
	render_fps: number;
	render_format: string;
	is_system: boolean;
	created_at: string;
	updated_at: string;
}

export interface ProfileTemplateCreate {
	name: string;
	category: string;
	description?: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	fps_mode?: string;
	render_target_seconds?: number;
	render_fps?: number;
	render_format?: string;
}

export interface ProfileCreate {
	name: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	weather_enabled?: boolean;
	ha_sensors?: string | null;
	capture_mode?: string;
	active_start_time?: string | null;
	active_end_time?: string | null;
	sun_offset_minutes?: number;
	sun_events?: string;
	ir_only?: boolean;
	ir_chroma_threshold?: number;
}

export interface ProfileUpdate {
	name?: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	weather_enabled?: boolean;
	ha_sensors?: string | null;
	enabled?: boolean;
	capture_mode?: string;
	active_start_time?: string | null;
	active_end_time?: string | null;
	sun_offset_minutes?: number;
	sun_events?: string;
	ir_only?: boolean;
	ir_chroma_threshold?: number;
}

export interface LocationConfig {
	latitude: number;
	longitude: number;
}

export interface Capture {
	id: number;
	profile_id: number;
	file_size: number | null;
	width: number | null;
	height: number | null;
	is_hdr: boolean;
	weather_temp: number | null;
	weather_code: number | null;
	captured_at: string;
	sensor_data?: string | null;
}

export interface Timelapse {
	id: number;
	profile_id: number;
	name: string | null;
	thumbnail_path: string | null;
	file_size: number | null;
	format: string;
	fps: number;
	frame_count: number | null;
	duration_seconds: number | null;
	period_type: string | null;
	period_start: string | null;
	period_end: string | null;
	created_at: string;
}

export interface TimelapseSchedule {
	id: number;
	profile_id: number;
	name: string;
	preset: string | null;
	cron_expression: string;
	fps: number;
	format: string;
	deflicker: string;
	lookback_hours: number | null;
	timestamp_overlay: boolean;
	weather_overlay: boolean;
	weather_position: string;
	weather_font_size: number;
	weather_unit: string;
	weather_style: string;
	ha_overlay?: boolean;
	ha_overlay_position?: string;
	heatmap_overlay: boolean;
	heatmap_mode: string;
	heatmap_colormap: string;
	heatmap_threshold: number;
	logo_overlay: boolean;
	logo_position: string;
	logo_size: number;
	logo_opacity: number;
	motion_blur: string;
	codec: string;
	output_width: number | null;
	output_height: number | null;
	quality_preset: string;
	enabled: boolean;
	created_at: string;
	updated_at: string;
	next_run: string | null;
}

export interface TimelapseScheduleCreate {
	profile_id: number;
	name?: string;
	preset?: string | null;
	cron_expression?: string | null;
	fps?: number;
	format?: string;
	deflicker?: string;
	lookback_hours?: number | null;
	timestamp_overlay?: boolean;
	weather_overlay?: boolean;
	weather_position?: string;
	weather_font_size?: number;
	weather_unit?: string;
	weather_style?: string;
	ha_overlay?: boolean;
	ha_overlay_position?: string;
	heatmap_overlay?: boolean;
	heatmap_mode?: string;
	heatmap_colormap?: string;
	heatmap_threshold?: number;
	logo_overlay?: boolean;
	logo_position?: string;
	logo_size?: number;
	logo_opacity?: number;
	motion_blur?: string;
	codec?: string;
	output_width?: number | null;
	output_height?: number | null;
	quality_preset?: string;
	enabled?: boolean;
}

export interface TimelapseScheduleUpdate {
	name?: string;
	preset?: string | null;
	cron_expression?: string | null;
	fps?: number;
	format?: string;
	deflicker?: string;
	lookback_hours?: number | null;
	timestamp_overlay?: boolean;
	weather_overlay?: boolean;
	weather_position?: string;
	weather_font_size?: number;
	weather_unit?: string;
	weather_style?: string;
	ha_overlay?: boolean;
	ha_overlay_position?: string;
	heatmap_overlay?: boolean;
	heatmap_mode?: string;
	heatmap_colormap?: string;
	heatmap_threshold?: number;
	logo_overlay?: boolean;
	logo_position?: string;
	logo_size?: number;
	logo_opacity?: number;
	motion_blur?: string;
	codec?: string;
	output_width?: number | null;
	output_height?: number | null;
	quality_preset?: string;
	enabled?: boolean;
}

export interface CleanupSchedule {
	id: number;
	profile_id: number;
	name: string;
	capture_retention_days: number;
	timelapse_retention_days: number;
	cron_expression: string;
	enabled: boolean;
	created_at: string;
	updated_at: string;
	next_run: string | null;
}

export interface CleanupScheduleCreate {
	profile_id: number;
	name?: string;
	capture_retention_days?: number;
	timelapse_retention_days?: number;
	cron_expression: string;
	enabled?: boolean;
}

export interface CleanupScheduleUpdate {
	name?: string;
	capture_retention_days?: number;
	timelapse_retention_days?: number;
	cron_expression?: string;
	enabled?: boolean;
}

export interface TimelapseGenerate {
	period_start?: string;
	period_end?: string;
	fps?: number;
	format?: string;
	deflicker?: string;
	timestamp_overlay?: boolean;
	weather_overlay?: boolean;
	weather_position?: string;
	weather_font_size?: number;
	weather_unit?: string;
	weather_style?: string;
	ha_overlay?: boolean;
	ha_overlay_position?: string;
	heatmap_overlay?: boolean;
	heatmap_mode?: string;
	heatmap_colormap?: string;
	heatmap_threshold?: number;
	logo_overlay?: boolean;
	logo_position?: string;
	logo_size?: number;
	logo_opacity?: number;
	motion_blur?: string;
	codec?: string;
	output_width?: number | null;
	output_height?: number | null;
	quality_preset?: string;
}

export interface TestResult {
	success: boolean;
	message: string;
	details?: Record<string, unknown>;
}

export interface StorageStats {
	captures_count: number;
	captures_size_bytes: number;
	timelapses_count: number;
	timelapses_size_bytes: number;
	total_size_bytes: number;
	disk_free_bytes: number;
	disk_total_bytes: number;
}

export interface Notification {
	id: number;
	event_type: string;
	title: string;
	body: string;
	level: string;
	read: boolean;
	created_at: string;
}

export interface NotificationURL {
	id: number;
	label: string;
	enabled: boolean;
	created_at: string;
}

export interface HealthConfig {
	check_interval_seconds: number;
	failure_threshold: number;
	low_disk_threshold_percent: number;
}

export interface NotificationEventsConfig {
	capture_failure: boolean;
	stream_unhealthy: boolean;
	stream_recovered: boolean;
	timelapse_started: boolean;
	timelapse_complete: boolean;
	timelapse_failure: boolean;
	timelapse_cancelled: boolean;
	retention_summary: boolean;
	low_disk_space: boolean;
	capture_gap: boolean;
	print_started: boolean;
	print_finished: boolean;
	print_failed: boolean;
}

export interface CaptureGapConfig {
	enabled: boolean;
}

export interface TimeFormatConfig {
	use_24h: boolean;
}

export interface StatsSummary {
	total_captures: number;
	avg_captures_per_day: number;
	avg_bytes_per_day: number;
	days_until_full: number | null;
}

export interface StorageTrendPoint {
	date: string;
	bytes_added: number;
	cumulative_bytes: number;
}

export interface CaptureActivityPoint {
	profile_id: number;
	date: string;
	count: number;
}

export interface ProfileStoragePoint {
	profile_id: number;
	date: string;
	bytes: number;
	count: number;
}

export interface TimelapseFormatBreakdown {
	format: string;
	count: number;
	total_size_bytes: number;
	total_duration_seconds: number;
}

export interface TimelapseSummary {
	total_count: number;
	total_size_bytes: number;
	total_frames: number;
	total_duration_seconds: number;
	by_format: TimelapseFormatBreakdown[];
}

export interface HomeAssistantConfig {
	base_url: string;
	configured?: boolean;
	connected?: boolean;
}

export interface PrusaLinkConfig {
	base_url: string;
	username: string;
	password?: string;
	stream_id: number | null;
	poll_interval_seconds: number;
	generate_on_finish: boolean;
	generate_on_cancel: boolean;
	enabled: boolean;
	clip_seconds: number;
	clip_fps: number;
	default_interval_seconds: number;
	min_interval_seconds: number;
	max_interval_seconds: number;
	timestamp_overlay: boolean;
	logo_overlay: boolean;
	deflicker: string;
	quality: number;
	ha_sensors: string | null;
	configured: boolean;
	connected: boolean;
}

export interface PrintJob {
	id: number;
	gcode_name: string;
	stream_id: number;
	status: 'printing' | 'finished' | 'cancelled';
	started_at: string;
	finished_at: string | null;
	estimated_seconds: number | null;
	interval_seconds: number | null;
	timelapse_id: number | null;
}

export interface HAEntity {
	entity_id: string;
	friendly_name: string;
	unit: string;
	device_class: string;
}

export interface HASensor {
	entity_id: string;
	label: string;
	unit: string;
	icon: string;
}
