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

function statusMeta(status: string): { label: string; cls: string } {
  switch (status) {
    case 'completed':   return { label: 'COMPLETE',   cls: 'ok' };
    case 'in_progress': return { label: 'IN PROGRESS', cls: 'live' };
    case 'failed':      return { label: 'FAILED',     cls: 'fail' };
    default:            return { label: status.toUpperCase(), cls: '' };
  }
}

export default function FlightHistory({ flights, onSelectFlight }: Props) {
  return (
    <div className="flight-history">
      <div className="history-header">
        <h2>MISSION LOG</h2>
        <div className="history-meta">
          <span className="history-count">{flights.length} ENTR{flights.length === 1 ? 'Y' : 'IES'}</span>
        </div>
      </div>

      {flights.length === 0 ? (
        <div className="no-flights">
          <div className="no-flights-frame">
            <span>NO MISSIONS LOGGED</span>
          </div>
        </div>
      ) : (
        <div className="flights-list">
          {flights.map((f, idx) => {
            const meta = statusMeta(f.status);
            const detectionDensity = f.framesProcessed > 0
              ? Math.min(1, f.pigeonsDetected / (f.framesProcessed / 30))
              : 0;
            return (
              <div
                key={f.id}
                className={`flight-card mission-card status-${meta.cls}`}
                onClick={() => onSelectFlight(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') onSelectFlight(f); }}
              >
                <div className="mission-card-stripe" aria-hidden="true" />

                <div className="mission-card-id">
                  <span className="mission-card-id-label">M-{String(flights.length - idx).padStart(3, '0')}</span>
                  <span className="mission-card-id-hash">#{f.id.substring(0, 8)}</span>
                </div>

                <div className="mission-card-body">
                  <div className="mission-card-row">
                    <span className="mission-card-date">{formatDate(f.startTime)}</span>
                    <span className={`mission-card-status status-pill-${meta.cls}`}>
                      <span className="mission-card-status-dot" />
                      {meta.label}
                    </span>
                  </div>

                  <div className="mission-card-stats">
                    <Stat label="DUR" value={formatDuration(f.duration)} />
                    <Stat label="FRAMES" value={f.framesProcessed.toLocaleString()} />
                    <Stat
                      label="HITS"
                      value={f.pigeonsDetected.toString()}
                      accent={f.pigeonsDetected > 0}
                    />
                  </div>

                  <div className="mission-card-bar">
                    <div className="mission-card-bar-label">DETECTION DENSITY</div>
                    <div className="mission-card-bar-track">
                      <div
                        className="mission-card-bar-fill"
                        style={{ width: `${detectionDensity * 100}%` }}
                      />
                      <div className="mission-card-bar-ticks">
                        {Array.from({ length: 20 }).map((_, i) => (
                          <span key={i} />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mission-card-action" aria-hidden="true">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M6 3 L11 8 L6 13" strokeLinecap="round" />
                  </svg>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`mission-stat ${accent ? 'mission-stat-accent' : ''}`}>
      <span className="mission-stat-label">{label}</span>
      <span className="mission-stat-value">{value}</span>
    </div>
  );
}
