import type { Stream, StreamCreate, StreamUpdate, Profile, ProfileCreate, ProfileUpdate, ProfileTemplate, ProfileTemplateCreate, Capture, Timelapse, TimelapseGenerate, TimelapseSchedule, TimelapseScheduleCreate, TimelapseScheduleUpdate, CleanupSchedule, CleanupScheduleCreate, CleanupScheduleUpdate, TestResult, StorageStats, Notification, NotificationURL, HealthConfig, NotificationEventsConfig, LocationConfig, CaptureGapConfig, StatsSummary, StorageTrendPoint, CaptureActivityPoint, ProfileStoragePoint, Go2rtcConfig, Go2rtcStreamInfo, TimelapseSummary } from './types';

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
	getSystemInfo: () => request<{ status: string; version: string; gpu_available: boolean; nvenc_available: boolean; nvenc_encoders: string[]; cupy_available: boolean }>('/system/info'),
	getActiveGenerations: () => request<any[]>('/generations/active'),

	// Streams
	getStreams: () => request<Stream[]>('/streams/'),
	getStream: (id: number) => request<Stream>(`/streams/${id}`),
	createStream: (data: StreamCreate) => request<Stream>('/streams/', { method: 'POST', body: JSON.stringify(data) }),
	updateStream: (id: number, data: StreamUpdate) => request<Stream>(`/streams/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteStream: (id: number) => request<void>(`/streams/${id}`, { method: 'DELETE' }),
	testStream: (id: number) => request<TestResult>(`/streams/${id}/test`, { method: 'POST' }),
	getStreamPreviewUrl: (id: number) => `${BASE}/streams/${id}/preview`,
	discoverGo2rtcStreams: () => request<Go2rtcStreamInfo[]>('/streams/go2rtc/discover'),
	getStreamLiveUrl: (id: number) => request<{ ws_url: string }>(`/streams/${id}/live-url`),

	// Profiles
	getStreamProfiles: (streamId: number) => request<Profile[]>(`/streams/${streamId}/profiles`),
	getProfile: (id: number) => request<Profile>(`/profiles/${id}`),
	createProfile: (streamId: number, data: ProfileCreate) => request<Profile>(`/streams/${streamId}/profiles`, { method: 'POST', body: JSON.stringify(data) }),
	updateProfile: (id: number, data: ProfileUpdate) => request<Profile>(`/profiles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteProfile: (id: number) => request<void>(`/profiles/${id}`, { method: 'DELETE' }),
	enableProfile: (id: number) => request<Profile>(`/profiles/${id}/enable`, { method: 'POST' }),
	disableProfile: (id: number) => request<Profile>(`/profiles/${id}/disable`, { method: 'POST' }),

	// Profile Templates
	getProfileTemplates: (category?: string) => {
		const qs = category ? `?category=${encodeURIComponent(category)}` : '';
		return request<ProfileTemplate[]>(`/profile-templates/${qs}`);
	},
	getProfileTemplate: (id: number) => request<ProfileTemplate>(`/profile-templates/${id}`),
	createProfileTemplate: (data: ProfileTemplateCreate) => request<ProfileTemplate>('/profile-templates/', { method: 'POST', body: JSON.stringify(data) }),
	updateProfileTemplate: (id: number, data: Partial<ProfileTemplateCreate>) => request<ProfileTemplate>(`/profile-templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteProfileTemplate: (id: number) => request<void>(`/profile-templates/${id}`, { method: 'DELETE' }),
	applyProfileTemplate: (id: number, streamId: number, name?: string) => request<Profile>(`/profile-templates/${id}/apply`, { method: 'POST', body: JSON.stringify({ stream_id: streamId, name }) }),

	// Captures
	getProfileCaptures: (profileId: number, limit = 50, offset = 0) => request<Capture[]>(`/profiles/${profileId}/captures?limit=${limit}&offset=${offset}`),
	getCaptureImageUrl: (id: number) => `${BASE}/captures/${id}/image`,
	deleteCapture: (id: number) => request<void>(`/captures/${id}`, { method: 'DELETE' }),
	bulkDeleteCaptures: (ids: number[]) => request<void>('/captures/bulk', { method: 'DELETE', body: JSON.stringify({ ids }) }),

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
	bulkDeleteTimelapses: (ids: number[]) => request<void>('/timelapses/bulk', { method: 'DELETE', body: JSON.stringify({ ids }) }),

	// Timelapse Schedules
	getTimelapseSchedules: (profileId?: number) => {
		const qs = profileId ? `?profile_id=${profileId}` : '';
		return request<TimelapseSchedule[]>(`/timelapse-schedules/${qs}`);
	},
	createTimelapseSchedule: (data: TimelapseScheduleCreate) => request<TimelapseSchedule>('/timelapse-schedules/', { method: 'POST', body: JSON.stringify(data) }),
	updateTimelapseSchedule: (id: number, data: TimelapseScheduleUpdate) => request<TimelapseSchedule>(`/timelapse-schedules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteTimelapseSchedule: (id: number) => request<void>(`/timelapse-schedules/${id}`, { method: 'DELETE' }),
	triggerTimelapseSchedule: (id: number) => request<{ status: string; message: string }>(`/timelapse-schedules/${id}/trigger`, { method: 'POST' }),

	// Cleanup Schedules
	getCleanupSchedules: (profileId?: number) => {
		const qs = profileId ? `?profile_id=${profileId}` : '';
		return request<CleanupSchedule[]>(`/cleanup-schedules/${qs}`);
	},
	createCleanupSchedule: (data: CleanupScheduleCreate) => request<CleanupSchedule>('/cleanup-schedules/', { method: 'POST', body: JSON.stringify(data) }),
	updateCleanupSchedule: (id: number, data: CleanupScheduleUpdate) => request<CleanupSchedule>(`/cleanup-schedules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteCleanupSchedule: (id: number) => request<void>(`/cleanup-schedules/${id}`, { method: 'DELETE' }),
	triggerCleanupSchedule: (id: number) => request<{ status: string; message: string }>(`/cleanup-schedules/${id}/trigger`, { method: 'POST' }),

	// Notifications
	getNotifications: (params?: { read?: boolean; limit?: number; offset?: number }) => {
		const sp = new URLSearchParams();
		if (params?.read !== undefined) sp.set('read', String(params.read));
		if (params?.limit) sp.set('limit', String(params.limit));
		if (params?.offset) sp.set('offset', String(params.offset));
		const qs = sp.toString();
		return request<Notification[]>(`/notifications/${qs ? '?' + qs : ''}`);
	},
	markNotificationRead: (id: number) => request<Notification>(`/notifications/${id}/read`, { method: 'PUT' }),
	markAllNotificationsRead: () => request<{ status: string }>('/notifications/read-all', { method: 'PUT' }),
	clearReadNotifications: () => request<void>('/notifications/read', { method: 'DELETE' }),
	deleteNotification: (id: number) => request<void>(`/notifications/${id}`, { method: 'DELETE' }),

	// Settings — Notifications
	getNotificationSettings: () => request<{ urls: NotificationURL[]; events: NotificationEventsConfig }>('/settings/notifications'),
	addNotificationURL: (data: { label: string; url: string }) => request<NotificationURL>('/settings/notifications/urls', { method: 'POST', body: JSON.stringify(data) }),
	updateNotificationURL: (id: number, data: { label?: string; enabled?: boolean }) => request<NotificationURL>(`/settings/notifications/urls/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteNotificationURL: (id: number) => request<void>(`/settings/notifications/urls/${id}`, { method: 'DELETE' }),
	testNotificationURL: (id: number) => request<{ success: boolean }>(`/settings/notifications/urls/${id}/test`, { method: 'POST' }),
	updateNotificationEvents: (data: NotificationEventsConfig) => request<NotificationEventsConfig>('/settings/notifications/events', { method: 'PUT', body: JSON.stringify(data) }),

	// Settings — Location
	getLocationConfig: () => request<LocationConfig>('/settings/location'),
	updateLocationConfig: (data: LocationConfig) => request<LocationConfig>('/settings/location', { method: 'PUT', body: JSON.stringify(data) }),

	// Settings — Health
	getHealthConfig: () => request<HealthConfig>('/settings/health'),
	updateHealthConfig: (data: HealthConfig) => request<HealthConfig>('/settings/health', { method: 'PUT', body: JSON.stringify(data) }),

	// Settings — go2rtc
	getGo2rtcConfig: () => request<Go2rtcConfig>('/settings/go2rtc'),
	updateGo2rtcConfig: (data: Go2rtcConfig) => request<Go2rtcConfig>('/settings/go2rtc', { method: 'PUT', body: JSON.stringify(data) }),
	testGo2rtcServer: (data: Go2rtcConfig) => request<TestResult>('/settings/go2rtc/test', { method: 'POST', body: JSON.stringify(data) }),

	// Settings — Capture Gap
	getCaptureGapConfig: () => request<CaptureGapConfig>('/settings/capture-gap'),
	updateCaptureGapConfig: (data: CaptureGapConfig) => request<CaptureGapConfig>('/settings/capture-gap', { method: 'PUT', body: JSON.stringify(data) }),

	// Statistics
	getStatsSummary: () => request<StatsSummary>('/statistics/summary'),
	getStorageTrend: (days = 90) => request<StorageTrendPoint[]>(`/statistics/storage-trend?days=${days}`),
	getCaptureActivity: (days = 30, profileId?: number) => {
		const sp = new URLSearchParams({ days: String(days) });
		if (profileId !== undefined) sp.set('profile_id', String(profileId));
		return request<CaptureActivityPoint[]>(`/statistics/capture-activity?${sp}`);
	},
	getProfileStorage: (days = 30, profileId?: number) => {
		const sp = new URLSearchParams({ days: String(days) });
		if (profileId !== undefined) sp.set('profile_id', String(profileId));
		return request<ProfileStoragePoint[]>(`/statistics/profile-storage?${sp}`);
	},
	getTimelapseSummary: () => request<TimelapseSummary>('/statistics/timelapse-summary'),

	// SSE helper
	getNotificationStreamUrl: () => `${BASE}/notifications/stream`,
};
