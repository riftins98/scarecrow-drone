import React from 'react';
import { Flight } from '../types/flight';

interface Props {
  flights: Flight[];
  onSelectFlight: (flight: Flight) => void;
}

function formatDuration(seconds: number): string {
  if (!seconds) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusStyle(status: string): React.CSSProperties {
  switch (status) {
    case 'completed': return { color: '#8b9a5b', borderColor: '#6a7b4a' };
    case 'in_progress': return { color: '#7a9a9a', borderColor: '#4a6a7b' };
    case 'failed': return { color: '#8b4a4a', borderColor: '#7b3a3a' };
    default: return {};
  }
}

export default function FlightHistory({ flights, onSelectFlight }: Props) {
  return (
    <div className="flight-history">
      <h2>Detection History</h2>
      {flights.length === 0 ? (
        <p className="no-flights">No detection sessions recorded</p>
      ) : (
        <div className="flights-list">
          {flights.map(f => (
            <div key={f.id} className="flight-card" onClick={() => onSelectFlight(f)}>
              <div className="flight-header">
                <span className="flight-date">{formatDate(f.startTime)}</span>
                <span className="flight-status" style={statusStyle(f.status)}>
                  {f.status.replace('_', ' ')}
                </span>
              </div>
              <div className="flight-details">
                <div className="detail">
                  <span className="label">Duration</span>
                  <span className="value">{formatDuration(f.duration)}</span>
                </div>
                <div className="detail">
                  <span className="label">Pigeons</span>
                  <span className="value pigeon-count">{f.pigeonsDetected}</span>
                </div>
                <div className="detail">
                  <span className="label">Frames</span>
                  <span className="value">{f.framesProcessed}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
