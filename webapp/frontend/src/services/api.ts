import { CameraInfo, ConnectSimParams, StartFlightParams } from '../types/flight';

/** Where the REST API lives.
 *
 *  Three cases, in order:
 *   - REACT_APP_API_BASE set (including to "") wins. The Docker build sets it
 *     to "" so requests are same-origin: the backend serves this bundle, so
 *     the API is wherever the page came from. Hardcoding a host there would
 *     break the moment the user opens the app from another machine, or from
 *     Windows against a container in WSL2.
 *   - Served from the backend itself (not the :3000 dev server) -> same-origin.
 *   - Otherwise the CRA dev server, where the backend is a separate process.
 *
 *  Note `??`, not `||`: "" is a meaningful value here and `||` would discard it.
 */
const DEV_SERVER_PORTS = ['3000'];

const API_BASE =
  process.env.REACT_APP_API_BASE ??
  (DEV_SERVER_PORTS.includes(window.location.port)
    ? 'http://127.0.0.1:8000'
    : '');

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
/** All stream cameras the headless launcher accepts (droplist source). */
export const getSimCameras = (): Promise<{ cameras: CameraInfo[] }> =>
  fetchJson('/api/sim/cameras');
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
export const simLogStreamUrl = (since: number = 0) =>
  `${API_BASE}/api/sim/log/stream?since=${since}`;

// Flight-script stdout — SystemLog after the sim is connected.
export const getFlightLog = (since: number = 0): Promise<LogPollResponse & { flight_id: string | null }> =>
  fetchJson(`/api/flight/log?since=${since}`);

export const flightLogViewUrl = () => `${API_BASE}/api/flight/log/view`;
export const flightLogStreamUrl = (since: number = 0) =>
  `${API_BASE}/api/flight/log/stream?since=${since}`;

// Flight history
export const getFlights = () => fetchJson('/api/flights');
export const getFlight = (id: string) => fetchJson(`/api/flights/${id}`);
export const getFlightImages = (id: string) => fetchJson(`/api/flights/${id}/images`);

// File URLs
export const detectionImageUrl = (flightId: string, filename: string) =>
  `${API_BASE}/detection_images/${flightId}/${filename}`;
export const missionMapUrl = (flightId: string, filename: string) =>
  `${API_BASE}/mission_maps/${flightId}/${filename}`;

/** Rewrite a backend-reported stream URL so it resolves from the browser.
 *
 *  The backend scrapes this out of the launcher banner, where it is always
 *  `http://localhost:<port>` because that is correct *on the sim host*. From
 *  any other machine -- a Windows browser pointed at a container in WSL2, or
 *  a phone on the LAN -- "localhost" is the browser's own machine and the feed
 *  is simply dead. The port is the part worth keeping; the host should be
 *  wherever the page itself came from.
 */
export function resolveStreamUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
      parsed.hostname = window.location.hostname;
    }
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return url;
  }
}
