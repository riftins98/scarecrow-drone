import React from 'react';
import { SimStatus, FlightStatus } from '../types/flight';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
  onConnect: () => void;
  onDisconnect: () => void;
  onStartFlight: () => void;
  onStopFlight: () => void;
  isConnecting: boolean;
  flightStartTime: Date | null;
}

export default function SimControl({
  simStatus, flightStatus, onConnect, onDisconnect,
  onStartFlight, onStopFlight, isConnecting, flightStartTime
}: Props) {
  const connected = simStatus?.connected || false;
  const launching = simStatus?.launching || false;
  const flying = flightStatus?.isFlying || false;
  const steps = simStatus?.progress?.steps || [];

  // Timer — compute initial value immediately to avoid flash to 00:00
  const calcElapsed = () => {
    if (!flightStartTime) return '00:00';
    const s = Math.floor((Date.now() - flightStartTime.getTime()) / 1000);
    const m = Math.floor(s / 60);
    return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };
  const [elapsed, setElapsed] = React.useState(calcElapsed);
  React.useEffect(() => {
    if (!flightStartTime) { setElapsed('00:00'); return; }
    setElapsed(calcElapsed());
    const interval = setInterval(() => setElapsed(calcElapsed()), 1000);
    return () => clearInterval(interval);
  }, [flightStartTime]);

  if (!connected) {
    return (
      <div className="drone-control">
        <h2>Simulation Control</h2>
        <div className="connection-panel">
          <div className="status-panel">
            <div className={`status-indicator ${launching ? 'connected' : 'disconnected'}`}>
              <span className="status-dot"></span>
              {launching ? 'Simulation Launching...' : 'Simulation Offline'}
            </div>
          </div>

          {launching ? (
            <div className="launch-checklist">
              {steps.map(step => (
                <div key={step.id} className={`checklist-item ${step.status}`}>
                  <span className="checklist-icon">
                    {step.status === 'done' ? '\u2713' :
                     step.status === 'active' ? '\u25CF' : '\u25CB'}
                  </span>
                  <span className="checklist-label">{step.label}</span>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p>Launch PX4 + Gazebo simulation to begin.</p>
              <div className="control-buttons">
                <button
                  className="btn btn-connect"
                  onClick={onConnect}
                  disabled={isConnecting}
                >
                  {isConnecting ? 'Launching...' : 'Connect'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="drone-control">
      <h2>Simulation Control</h2>
      <div className="status-panel">
        <div className="status-indicator connected">
          <span className="status-dot"></span>
          Simulation Online
        </div>
      </div>

      <div className="control-buttons">
        {!flying ? (
          <button className="btn btn-start" onClick={onStartFlight}>
            Start Detection
          </button>
        ) : (
          <button className="btn btn-stop" onClick={onStopFlight}>
            Stop Detection
          </button>
        )}
        <button className="btn btn-disconnect" onClick={onDisconnect} disabled={flying}>
          Disconnect
        </button>
      </div>

      {flying && (
        <div className="flight-status">
          <div className="flight-timer">
            <span className="timer-label">Detection Time</span>
            <span className="timer-value">{elapsed}</span>
          </div>
          <div className="flight-indicator">
            <span className="pulse"></span>
            Detection in progress
          </div>
          {flightStatus && (
            <div className="flight-details" style={{ marginTop: 15, justifyContent: 'center' }}>
              <div className="detail">
                <span className="label">Frames</span>
                <span className="value">{flightStatus.frames_processed}</span>
              </div>
              <div className="detail">
                <span className="label">Pigeons</span>
                <span className="value pigeon-count">{flightStatus.pigeons_detected}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
