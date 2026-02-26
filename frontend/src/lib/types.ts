export interface Stream {
	id: number;
	name: string;
	enabled: boolean;
	created_at: string;
	updated_at: string;
}

export interface StreamCreate {
	name: string;
	url: string;
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
	enabled: boolean;
	created_at: string;
	updated_at: string;
}

export interface ProfileCreate {
	name: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
}

export interface ProfileUpdate {
	name?: string;
	interval_seconds?: number;
	resolution_width?: number | null;
	resolution_height?: number | null;
	quality?: number;
	hdr_enabled?: boolean;
	enabled?: boolean;
}

export interface Capture {
	id: number;
	profile_id: number;
	file_size: number | null;
	width: number | null;
	height: number | null;
	is_hdr: boolean;
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

export interface TimelapseGenerate {
	period_start?: string;
	period_end?: string;
	fps?: number;
	format?: string;
	timestamp_overlay?: boolean;
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
