import type { Stream, StreamCreate, StreamUpdate, TestResult } from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...options?.headers },
		...options
	});
	if (!res.ok) throw new Error(`API error: ${res.status}`);
	return res.json();
}

export const api = {
	// Streams
	getStreams: () => request<Stream[]>('/streams'),
	getStream: (id: number) => request<Stream>(`/streams/${id}`),
	createStream: (data: StreamCreate) =>
		request<Stream>('/streams', { method: 'POST', body: JSON.stringify(data) }),
	updateStream: (id: number, data: StreamUpdate) =>
		request<Stream>(`/streams/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	deleteStream: (id: number) => request<void>(`/streams/${id}`, { method: 'DELETE' }),
	testStream: (id: number) => request<TestResult>(`/streams/${id}/test`, { method: 'POST' }),

	// Health
	getHealth: () => request<{ status: string; version: string }>('/health')
};
