import React, { useEffect, useState } from 'react';
import {
  SimStatus,
  FlightStatus,
  SimOptions,
  ScriptInfo,
  ScriptArg,
  ScriptArgValues,
  ConnectSimParams,
  StartFlightParams,
  WorldInfo,
  CameraInfo,
} from '../types/flight';
import * as api from '../services/api';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
  onConnect: (params: ConnectSimParams) => void;
  onDisconnect: () => void;
  onStartFlight: (params: StartFlightParams) => void;
  onStopFlight: () => void;
  isConnecting: boolean;
  flightStartTime: Date | null;
}

const DEFAULT_WORLD = 'drone_garage_pigeon_3d';
const DEFAULT_SCRIPT = 'demo_flight_v2.py';

export default function SimControl({
  simStatus, flightStatus, onConnect, onDisconnect,
  onStartFlight, onStopFlight, isConnecting, flightStartTime,
}: Props) {
  const connected = simStatus?.connected || false;
  const launching = simStatus?.launching || false;
  const flying = flightStatus?.isFlying || false;
  const steps = simStatus?.progress?.steps || [];

  // Sim options (worlds + scripts) — fetched once on mount
  const [options, setOptions] = useState<SimOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // Pre-connect form state
  const [selectedWorld, setSelectedWorld] = useState<string>(DEFAULT_WORLD);
  const [headless, setHeadless] = useState<boolean>(false);
  // Camera the user picked from the dropdown (only meaningful in headless mode).
  // Empty string -> "let backend default it" (currently "fixed").
  const [selectedCamera, setSelectedCamera] = useState<string>('');

  // Post-connect form state
  const [selectedScript, setSelectedScript] = useState<string>(DEFAULT_SCRIPT);
  const [scriptArgValues, setScriptArgValues] = useState<ScriptArgValues>({});

  useEffect(() => {
    api.getSimOptions()
      .then((data: SimOptions) => {
        setOptions(data);
        // If our default world isn't actually available, fall back to the first.
        if (data.worlds.length > 0 && !data.worlds.find((w: { name: string }) => w.name === DEFAULT_WORLD)) {
          setSelectedWorld(data.worlds[0].name);
        }
        if (data.scripts.length > 0 && !data.scripts.find((s: { name: string }) => s.name === DEFAULT_SCRIPT)) {
          setSelectedScript(data.scripts[0].name);
        }
      })
      .catch((e: unknown) => setOptionsError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Cameras the selected world exposes (parsed from its SDF by the backend).
  // Empty if the SDF has no streamable cameras — in that case the headless
  // launcher will still fall back to "fixed" if the user picks headless.
  const availableCameras = options?.worlds.find(
    (w: WorldInfo) => w.name === selectedWorld,
  )?.cameras ?? [];

  // Sync the camera selection with the current world. When the world
  // changes (or options first arrive), reset to the first available camera
  // if the previous pick isn't in the new world.
  useEffect(() => {
    if (availableCameras.length === 0) {
      setSelectedCamera('');
      return;
    }
    if (!availableCameras.find((c: CameraInfo) => c.name === selectedCamera)) {
      setSelectedCamera(availableCameras[0].name);
    }
    // selectedCamera intentionally omitted from deps: we only reseed it when
    // the available-set changes (world swap), not on every user click.
  }, [selectedWorld, options]);

  // When the selected script changes, reset arg values to that script's defaults
  // (so the form fields reflect the new arg set, not stale values from another script).
  useEffect(() => {
    if (!options) return;
    const script = options.scripts.find((s: ScriptInfo) => s.name === selectedScript);
    if (!script) {
      setScriptArgValues({});
      return;
    }
    const initial: ScriptArgValues = {};
    for (const a of script.args) {
      // Skip flight-id: backend always supplies it
      if (a.name === 'flight_id' || a.name === 'flight-id') continue;
      initial[a.name] = a.default ?? (a.type === 'bool' ? false : '');
    }
    setScriptArgValues(initial);
  }, [selectedScript, options]);

  // Live timer for the post-takeoff "detection time" display.
  const calcElapsed = () => {
    if (!flightStartTime) return '00:00';
    const s = Math.floor((Date.now() - flightStartTime.getTime()) / 1000);
    const m = Math.floor(s / 60);
    return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };
  const [elapsed, setElapsed] = useState(calcElapsed);
  useEffect(() => {
    if (!flightStartTime) { setElapsed('00:00'); return; }
    setElapsed(calcElapsed());
    const interval = setInterval(() => setElapsed(calcElapsed()), 1000);
    return () => clearInterval(interval);
  }, [flightStartTime]);

  const handleConnect = () => {
    const params: ConnectSimParams = { world: selectedWorld, headless };
    if (headless && selectedCamera) {
      params.camera = selectedCamera;
    }
    onConnect(params);
  };

  const handleStart = () => {
    // Strip out empty-string values so the script uses its built-in defaults
    // for fields the user left blank.
    const cleanedArgs: ScriptArgValues = {};
    for (const k of Object.keys(scriptArgValues)) {
      const v = scriptArgValues[k];
      if (v === '' || v === null || v === undefined) continue;
      cleanedArgs[k] = v;
    }
    onStartFlight({ script: selectedScript, args: cleanedArgs });
  };

  const updateArg = (name: string, value: ScriptArgValues[string]) => {
    setScriptArgValues((prev: ScriptArgValues) => ({ ...prev, [name]: value }));
  };

  // ----- PRE-CONNECT view -----
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
              {steps.map((step: import('../types/flight').LaunchStep) => (
                <div key={step.id} className={`checklist-item ${step.status}`}>
                  <span className="checklist-icon" aria-hidden="true">
                    <ChecklistIcon status={step.status} />
                  </span>
                  <div className="checklist-text">
                    <span className="checklist-label">{step.label}</span>
                    {step.status === 'active' && step.substatus && (
                      <span className="checklist-substatus">{step.substatus}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p>Configure the simulation, then launch PX4 + Gazebo.</p>

              {optionsError && (
                <div className="error-message">
                  Could not load sim options: {optionsError}
                </div>
              )}

              <div className="sim-config-form">
                <label className="form-row">
                  <span className="form-label">World</span>
                  <select
                    value={selectedWorld}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedWorld(e.target.value)}
                    disabled={!options}
                  >
                    {options ? options.worlds.map((w: WorldInfo) => (
                      <option key={w.name} value={w.name}>{w.name}</option>
                    )) : <option>Loading...</option>}
                  </select>
                </label>

                <fieldset className="form-row">
                  <legend className="form-label">Display</legend>
                  <label className="radio-option">
                    <input
                      type="radio"
                      name="display-mode"
                      checked={!headless}
                      onChange={() => setHeadless(false)}
                    />
                    GUI (open Gazebo window)
                  </label>
                  <label className="radio-option">
                    <input
                      type="radio"
                      name="display-mode"
                      checked={headless}
                      onChange={() => setHeadless(true)}
                    />
                    Headless (browser camera stream)
                  </label>
                </fieldset>

                {headless && (
                  <label className="form-row">
                    <span className="form-label">Stream camera</span>
                    {availableCameras.length === 0 ? (
                      <span className="form-hint">
                        No streamable cameras in this world — launcher will use default ("fixed")
                      </span>
                    ) : (
                      <select
                        value={selectedCamera}
                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedCamera(e.target.value)}
                        disabled={!options}
                      >
                        {availableCameras.map((c: CameraInfo) => (
                          <option key={c.name} value={c.name}>
                            {c.label} ({c.name})
                          </option>
                        ))}
                      </select>
                    )}
                  </label>
                )}
              </div>

              <div className="control-buttons">
                <button
                  className="btn btn-connect"
                  onClick={handleConnect}
                  disabled={isConnecting || !options}
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

  // ----- POST-CONNECT view -----
  const currentScript: ScriptInfo | undefined =
    options?.scripts.find((s: ScriptInfo) => s.name === selectedScript);

  return (
    <div className="drone-control">
      <h2>Simulation Control</h2>
      <div className="status-panel status-panel-stacked">
        <div className="status-indicator connected">
          <span className="status-dot"></span>
          Simulation Online
        </div>
        {simStatus?.world && (
          <div className="status-line">World: {simStatus.world}</div>
        )}
        {simStatus?.headless && (
          <div className="status-line">Headless</div>
        )}
      </div>

      {/* Script selector and arg form (hidden while flying) */}
      {!flying && (
        <div className="script-config">
          <label className="form-row">
            <span className="form-label">Flight script</span>
            <select
              value={selectedScript}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedScript(e.target.value)}
              disabled={!options}
            >
              {options ? options.scripts.map((s: ScriptInfo) => (
                <option key={s.name} value={s.name}>
                  {s.name}{s.parse_error ? ' (no parameters)' : ''}
                </option>
              )) : <option>Loading...</option>}
            </select>
          </label>

          {currentScript?.description && (
            <p className="script-description">{currentScript.description}</p>
          )}

          {currentScript?.parse_error && (
            <p className="script-warning">
              Note: could not parse this script's arguments — it will run with defaults.
            </p>
          )}

          {currentScript && currentScript.args.length > 0 && (
            <div className="script-args">
              <div className="form-label">Parameters</div>
              {currentScript.args
                .filter((a: ScriptArg) => a.name !== 'flight_id')
                .map((arg: ScriptArg) => (
                  <ArgField
                    key={arg.name}
                    arg={arg}
                    value={scriptArgValues[arg.name] as ScriptArgValues[string]}
                    onChange={(v: ScriptArgValues[string]) => updateArg(arg.name, v)}
                  />
                ))}
            </div>
          )}
        </div>
      )}

      <div className="control-buttons">
        {!flying ? (
          <button className="btn btn-start" onClick={handleStart}>
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


function ChecklistIcon({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <svg viewBox="0 0 14 14" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 7.5 L5.5 11 L12 3" />
      </svg>
    );
  }
  if (status === 'active') {
    return (
      <svg viewBox="0 0 14 14" fill="currentColor" stroke="none">
        <circle cx="7" cy="7" r="3.5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 14 14" fill="none" strokeWidth="1.5">
      <circle cx="7" cy="7" r="4" />
    </svg>
  );
}


interface ArgFieldProps {
  arg: ScriptArg;
  value: ScriptArgValues[string];
  onChange: (v: ScriptArgValues[string]) => void;
}

function ArgField({ arg, value, onChange }: ArgFieldProps) {
  const label = arg.flag.replace(/^-+/, '');

  if (arg.type === 'bool') {
    return (
      <label className="arg-field arg-bool">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
        />
        <span className="arg-label">{label}</span>
        {arg.help && <span className="arg-help"> — {arg.help}</span>}
      </label>
    );
  }

  if (arg.type === 'choice' && arg.choices) {
    return (
      <label className="arg-field">
        <span className="arg-label">{label}</span>
        <select
          value={(value as string) ?? ''}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value || null)}
        >
          <option value="">(default)</option>
          {arg.choices.map((c: string) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        {arg.help && <span className="arg-help">{arg.help}</span>}
      </label>
    );
  }

  const isNumeric = arg.type === 'int' || arg.type === 'float';
  const inputType = isNumeric ? 'number' : 'text';
  const step = arg.type === 'float' ? 'any' : (arg.type === 'int' ? '1' : undefined);
  const placeholder = arg.default !== null && arg.default !== undefined
    ? `default: ${arg.default}`
    : '(no default)';

  return (
    <label className="arg-field">
      <span className="arg-label">{label}</span>
      <input
        type={inputType}
        step={step}
        placeholder={placeholder}
        value={value === null || value === undefined || value === false ? '' : String(value)}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          const v = e.target.value;
          if (v === '') onChange('');
          else if (arg.type === 'int') onChange(parseInt(v, 10));
          else if (arg.type === 'float') onChange(parseFloat(v));
          else onChange(v);
        }}
      />
      {arg.help && <span className="arg-help">{arg.help}</span>}
    </label>
  );
}
