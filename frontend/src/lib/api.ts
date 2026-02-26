import type { Stream, StreamCreate, StreamUpdate, Profile, ProfileCreate, ProfileUpdate, Capture, Timelapse, TimelapseGenerate, TestResult, StorageStats } from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...options?.headers },
		...options
	});
	if (!res.ok) {
		const text = await res.text().catch(() => '');
		throw new Error(`API error ${res.status}: ${text}`);
	}
	if (res.status === 204) return undefined as T;
	return res.json();
}

export const api = {
	// Health
	getHealth: () => request<{ status: string; version: string }>('/health'),
	getStorage: () => request<StorageStats>('/storage'),

	// Streams
	getStreams: () => request<Stream[]>('/streams/'),
	getStream: (id: number) => request<Stream>(`/streams/${id}`),
	createStream: (data: StreamCreate) => request<Stream>('/streams/', { method: 'POST', body: JSON.stringify(data) }),
	updateStream: (id: number, data: StreamUpdate) => request<Stream>(`/streams/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteStream: (id: number) => request<void>(`/streams/${id}`, { method: 'DELETE' }),
	testStream: (id: number) => request<TestResult>(`/streams/${id}/test`, { method: 'POST' }),
	getStreamPreviewUrl: (id: number) => `${BASE}/streams/${id}/preview`,

	// Profiles
	getStreamProfiles: (streamId: number) => request<Profile[]>(`/streams/${streamId}/profiles`),
	getProfile: (id: number) => request<Profile>(`/profiles/${id}`),
	createProfile: (streamId: number, data: ProfileCreate) => request<Profile>(`/streams/${streamId}/profiles`, { method: 'POST', body: JSON.stringify(data) }),
	updateProfile: (id: number, data: ProfileUpdate) => request<Profile>(`/profiles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteProfile: (id: number) => request<void>(`/profiles/${id}`, { method: 'DELETE' }),
	enableProfile: (id: number) => request<Profile>(`/profiles/${id}/enable`, { method: 'POST' }),
	disableProfile: (id: number) => request<Profile>(`/profiles/${id}/disable`, { method: 'POST' }),

	// Captures
	getProfileCaptures: (profileId: number, limit = 50, offset = 0) => request<Capture[]>(`/profiles/${profileId}/captures?limit=${limit}&offset=${offset}`),
	getCaptureImageUrl: (id: number) => `${BASE}/captures/${id}/image`,
	deleteCapture: (id: number) => request<void>(`/captures/${id}`, { method: 'DELETE' }),

	// Timelapses
	getTimelapses: (params?: { profile_id?: number; period_type?: string; limit?: number; offset?: number }) => {
		const searchParams = new URLSearchParams();
		if (params?.profile_id) searchParams.set('profile_id', String(params.profile_id));
		if (params?.period_type) searchParams.set('period_type', params.period_type);
		if (params?.limit) searchParams.set('limit', String(params.limit));
		if (params?.offset) searchParams.set('offset', String(params.offset));
		const qs = searchParams.toString();
		return request<Timelapse[]>(`/timelapses${qs ? '?' + qs : ''}`);
	},
	getTimelapse: (id: number) => request<Timelapse>(`/timelapses/${id}`),
	getTimelapseVideoUrl: (id: number) => `${BASE}/timelapses/${id}/video`,
	generateTimelapse: (profileId: number, data: TimelapseGenerate) => request<{ status: string; message: string }>(`/profiles/${profileId}/timelapses/generate`, { method: 'POST', body: JSON.stringify(data) }),
	deleteTimelapse: (id: number) => request<void>(`/timelapses/${id}`, { method: 'DELETE' }),
};
