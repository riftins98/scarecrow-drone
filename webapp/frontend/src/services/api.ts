import { ConnectSimParams, StartFlightParams } from '../types/flight';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://127.0.0.1:8000';

/** Thrown for any non-2xx response; carries the HTTP status so callers can
 *  branch on it (e.g. polling code that should back off on 404). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function fetchJson(url: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail || err.error || res.statusText);
  }
  return res.json();
}

function postJson<T>(url: string, body?: T) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

// Sim connection
export const connectSim = (params?: ConnectSimParams) =>
  postJson('/api/sim/connect', params || {});
export const disconnectSim = () => fetchJson('/api/sim/connect', { method: 'DELETE' });
export const getSimStatus = () => fetchJson('/api/sim/status');
export const getSimOptions = () => fetchJson('/api/sim/options');
/** Live-swap the headless camera without restarting PX4/Gazebo. */
export const setSimCamera = (camera: string): Promise<{
  success: boolean;
  camera?: string;
  error?: string;
  noop?: boolean;
}> => postJson('/api/sim/camera', { camera });

// Flight control
export const startFlight = (params?: StartFlightParams) =>
  postJson('/api/flight/start', params || {});
export const stopFlight = () => fetchJson('/api/flight/stop', { method: 'POST' });
export const getFlightStatus = () => fetchJson('/api/flight/status');

// Sim launcher stdout. Polled by SystemLog with the last cursor.
// Shows PX4 build, Gazebo start, and other launcher output during connect.
export const getSimLog = (since: number = 0): Promise<{
  lines: string[];
  start: number;
  cursor: number;
  dropped: number;
  running: boolean;
  world: string;
}> => fetchJson(`/api/sim/log?since=${since}`);

// URL of the standalone full-page log view (opens in a new browser tab).
export const simLogViewUrl = () => `${API_BASE}/api/sim/log/view`;

// Flight history
export const getFlights = () => fetchJson('/api/flights');
export const getFlight = (id: string) => fetchJson(`/api/flights/${id}`);
export const getFlightImages = (id: string) => fetchJson(`/api/flights/${id}/images`);
export const getFlightRecording = (id: string) => fetchJson(`/api/flights/${id}/recording`);

// File URLs
export const detectionImageUrl = (flightId: string, filename: string) =>
  `${API_BASE}/detection_images/${flightId}/${filename}`;
export const recordingUrl = (flightId: string, filename: string) =>
  `${API_BASE}/recordings/${flightId}/${filename}`;
