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

/** Re-spawn the drone at (x, y) on a running mapped world. Validates wall and
 *  obstacle clearance, teleports, and moves where the panic reset returns. */
export const setSpawn = (x: number, y: number): Promise<{
  success: boolean;
  spawn?: { x: number; y: number };
  error?: string;
}> => postJson('/api/sim/spawn', { x, y });

// Flight control
export const startFlight = (params?: StartFlightParams) =>
  postJson('/api/flight/start', params || {});
export const stopFlight = () => fetchJson('/api/flight/stop', { method: 'POST' });
export const getFlightStatus = () => fetchJson('/api/flight/status');

/** Panic reset: hard-kill the flight, force-disarm, and teleport the drone
 *  back to its spawn pose in the world. */
export const resetDrone = (): Promise<{
  success: boolean;
  killedFlight?: boolean;
  disarmed?: boolean;
  teleport?: { success: boolean; model?: string; error?: string };
  error?: string;
}> => postJson('/api/sim/reset');

export interface LogPollResponse {
  lines: string[];
  start: number;
  cursor: number;
  dropped: number;
  running: boolean;
}

// Sim launcher stdout — SystemLog while connecting (pre-drone).
export const getSimLog = (since: number = 0): Promise<LogPollResponse & { world: string }> =>
  fetchJson(`/api/sim/log?since=${since}`);

export const simLogViewUrl = () => `${API_BASE}/api/sim/log/view`;

// Flight-script stdout — SystemLog after the sim is connected.
export const getFlightLog = (since: number = 0): Promise<LogPollResponse & { flight_id: string | null }> =>
  fetchJson(`/api/flight/log?since=${since}`);

export const flightLogViewUrl = () => `${API_BASE}/api/flight/log/view`;

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
export const missionMapUrl = (flightId: string, filename: string) =>
  `${API_BASE}/mission_maps/${flightId}/${filename}`;
