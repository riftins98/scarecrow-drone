const API_BASE = 'http://localhost:5000';

async function fetchJson(url: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || res.statusText);
  }
  return res.json();
}

// Sim connection
export const connectSim = () => fetchJson('/api/sim/connect', { method: 'POST' });
export const disconnectSim = () => fetchJson('/api/sim/connect', { method: 'DELETE' });
export const getSimStatus = () => fetchJson('/api/sim/status');

// Flight control
export const startFlight = () => fetchJson('/api/flight/start', { method: 'POST' });
export const stopFlight = () => fetchJson('/api/flight/stop', { method: 'POST' });
export const getFlightStatus = () => fetchJson('/api/flight/status');

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
