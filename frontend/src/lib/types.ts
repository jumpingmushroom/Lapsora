export interface Stream {
	id: number;
	name: string;
	source_type: string;
	go2rtc_name: string | null;
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
	source_type?: 'rtsp' | 'go2rtc';
	go2rtc_name?: string;
}

export interface Go2rtcConfig {
	url: string;
}

export interface Go2rtcStreamInfo {
	name: string;
	producers: unknown[];
}

export interface StreamUpdate {
	name?: string;
	url?: string;
	enabled?: boolean;
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
	enabled: boolean;
	auto_disabled: boolean;
	capture_mode: string;
	active_start_time: string | null;
	active_end_time: string | null;
	sun_offset_minutes: number;
	source_template_id: number | null;
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
}

export interface ProfileCreate {
	name: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	weather_enabled?: boolean;
	capture_mode?: string;
	active_start_time?: string | null;
	active_end_time?: string | null;
	sun_offset_minutes?: number;
}

export interface ProfileUpdate {
	name?: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	weather_enabled?: boolean;
	enabled?: boolean;
	capture_mode?: string;
	active_start_time?: string | null;
	active_end_time?: string | null;
	sun_offset_minutes?: number;
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
}

export interface Timelapse {
	id: number;
	profile_id: number;
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
	lookback_hours: number | null;
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
	lookback_hours?: number;
	enabled?: boolean;
}

export interface TimelapseScheduleUpdate {
	name?: string;
	preset?: string | null;
	cron_expression?: string | null;
	fps?: number;
	format?: string;
	lookback_hours?: number;
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
	timestamp_overlay?: boolean;
	weather_overlay?: boolean;
	weather_position?: string;
	weather_font_size?: number;
	weather_unit?: string;
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
	timelapse_complete: boolean;
	timelapse_failure: boolean;
	retention_summary: boolean;
	low_disk_space: boolean;
	capture_gap: boolean;
}

export interface CaptureGapConfig {
	enabled: boolean;
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
