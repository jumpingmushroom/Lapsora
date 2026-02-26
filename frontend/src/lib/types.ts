export interface Stream {
	id: number;
	name: string;
	url: string;
	enabled: boolean;
	profile_id: number | null;
	created_at: string;
	updated_at: string;
}

export interface StreamCreate {
	name: string;
	url: string;
	enabled?: boolean;
	profile_id?: number | null;
}

export interface StreamUpdate {
	name?: string;
	url?: string;
	enabled?: boolean;
	profile_id?: number | null;
}

export interface Profile {
	id: number;
	name: string;
	interval_seconds: number;
	output_fps: number;
	resolution: string | null;
	created_at: string;
	updated_at: string;
}

export interface ProfileCreate {
	name: string;
	interval_seconds: number;
	output_fps: number;
	resolution?: string | null;
}

export interface ProfileUpdate {
	name?: string;
	interval_seconds?: number;
	output_fps?: number;
	resolution?: string | null;
}

export interface Capture {
	id: number;
	stream_id: number;
	filepath: string;
	captured_at: string;
}

export interface Timelapse {
	id: number;
	stream_id: number;
	filepath: string;
	frame_count: number;
	duration_seconds: number;
	created_at: string;
}

export interface TestResult {
	success: boolean;
	message: string;
	details?: string;
}
