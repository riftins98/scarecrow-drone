import React, { useEffect, useId, useRef, useState } from 'react';
import {
  SimStatus,
  FlightStatus,
  SimOptions,
  ScriptArg,
  ScriptArgValues,
  ConnectSimParams,
  StartFlightParams,
  WorldInfo,
  CameraInfo,
  SpawnPoint,
} from '../types/flight';
import * as api from '../services/api';
import { spawnMapForWorld } from './spawnMapLookup';
import { defaultWorldFromOptions, worldLabelFor } from './worldLabels';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
  onConnect: (params: ConnectSimParams) => void;
  onDisconnect: () => void;
  onStartFlight: (params: StartFlightParams) => void;
  onStopFlight: () => void;
  isConnecting: boolean;
  flightStartTime: Date | null;
  selectedSpawn?: SpawnPoint | null;
  onPreviewWorldChange?: (world: string) => void;
}

/** Hardcoded mission entrypoint — not exposed as a user-facing script picker. */
const PURSUIT_FLIGHT_SCRIPT = 'hangar_circuit_pursuit.py';

const PURSUIT_MISSION_ARGS: ScriptArg[] = [
  {
    name: 'wall_distance',
    flag: '--wall-distance',
    type: 'float',
    default: 2.0,
    help: 'Standoff distance from the wall during hangar circuit legs (meters).',
  },
  {
    name: 'ceiling_clearance',
    flag: '--ceiling-clearance',
    type: 'float',
    default: null,
    help: 'Optional minimum ceiling clearance for in-flight safety checks (meters).',
  },
  {
    name: 'start_side',
    flag: '--start-side',
    type: 'choice',
    default: 'left',
    help: 'Initial rear corner used before the left-wall scan begins.',
    choices: ['left', 'right'],
  },
];

function formatArgLabel(flagOrName: string): string {
  const raw = flagOrName.replace(/^--+/, '');
  return raw
    .split(/[-_]/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function defaultPursuitArgValues(): ScriptArgValues {
  const initial: ScriptArgValues = {};
  for (const arg of PURSUIT_MISSION_ARGS) {
    initial[arg.name] = arg.default ?? (arg.type === 'bool' ? false : '');
  }
  return initial;
}

export default function SimControl({
  simStatus, flightStatus, onConnect, onDisconnect,
  onStartFlight, onStopFlight, isConnecting, flightStartTime,
  selectedSpawn,
  onPreviewWorldChange,
}: Props) {
  const connected = simStatus?.connected || false;
  const launching = simStatus?.launching || false;
  const flying = flightStatus?.isFlying || false;
  const steps = simStatus?.progress?.steps || [];

  // Sim options (worlds + scripts) — fetched once on mount
  const [options, setOptions] = useState<SimOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [streamCameras, setStreamCameras] = useState<CameraInfo[]>([]);

  // Pre-connect form state
  const [selectedWorld, setSelectedWorld] = useState<string>('');
  const [headless, setHeadless] = useState<boolean>(false);
  // Camera the user picked from the dropdown (only meaningful in headless mode).
  // Empty string -> "let backend default it" (currently "fixed").
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  // Post-connect pursuit parameters (hardcoded mission — no script picker).
  const [scriptArgValues, setScriptArgValues] = useState<ScriptArgValues>(defaultPursuitArgValues);

  // Panic reset state.
  const [resetting, setResetting] = useState<boolean>(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  const handleReset = async () => {
    if (resetting) return;
    setResetMsg(null);
    setResetting(true);
    try {
      const res = await api.resetDrone();
      if (res.success) {
        setResetMsg('Drone reset to spawn.');
      } else {
        setResetMsg(`Reset failed: ${res.error || 'unknown error'}`);
      }
    } catch (e) {
      setResetMsg(`Reset failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setResetting(false);
      // Auto-clear the status line after a few seconds.
      window.setTimeout(() => setResetMsg(null), 5000);
    }
  };

  useEffect(() => {
    Promise.all([api.getSimOptions(), api.getSimCameras()])
      .then(([data, camerasRes]) => {
        setOptions(data);
        setStreamCameras(camerasRes.cameras);
        const preferred = defaultWorldFromOptions(data);
        setSelectedWorld((current) => {
          if (current && data.worlds.some((w: WorldInfo) => w.name === current)) {
            return current;
          }
          return preferred;
        });
      })
      .catch((e: unknown) => setOptionsError(e instanceof Error ? e.message : String(e)));
  }, []);

  const availableCameras = streamCameras;

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
    // selectedCamera intentionally omitted from deps: we only reseed when the
    // camera list first arrives or shrinks, not on every user click.
  }, [availableCameras]);

  useEffect(() => {
    onPreviewWorldChange?.(selectedWorld);
  }, [selectedWorld, onPreviewWorldChange]);

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

  const selectedSpawnMap = spawnMapForWorld(options, selectedWorld);
  const spawnSupported = !!selectedSpawnMap;

  const handleConnect = () => {
    const params: ConnectSimParams = { world: selectedWorld, headless };
    if (headless && selectedCamera) {
      params.camera = selectedCamera;
    }
    if (spawnSupported && selectedSpawn) {
      params.spawn = selectedSpawn;
    }
    onConnect(params);
  };

  const handleWorldChange = (world: string) => {
    setSelectedWorld(world);
    onPreviewWorldChange?.(world);
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
    onStartFlight({ script: PURSUIT_FLIGHT_SCRIPT, args: cleanedArgs });
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

              <div className="sim-config-layout">
                <div className="sim-config-form">
                <label className="form-row">
                  <span className="form-label">World</span>
                  <HudSelect
                    value={selectedWorld}
                    onChange={handleWorldChange}
                    disabled={!options}
                    options={options
                      ? options.worlds.map((w: WorldInfo) => ({ value: w.name, label: w.label }))
                      : [{ value: '', label: 'Loading...' }]}
                  />
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
                        No stream cameras found — launcher will use default ("fixed")
                      </span>
                    ) : (
                      <HudSelect
                        value={selectedCamera}
                        onChange={setSelectedCamera}
                        disabled={!options}
                        options={availableCameras.map((c: CameraInfo) => ({
                          value: c.name,
                          label: c.label,
                        }))}
                      />
                    )}
                  </label>
                )}

                </div>
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
  return (
    <div className="drone-control">
      <h2>Pigeon Pursuit</h2>
      <div className="status-panel status-panel-stacked">
        <div className="status-indicator connected">
          <span className="status-dot"></span>
          Simulation Online
        </div>
        {simStatus?.world && (
          <div className="status-line">World: {worldLabelFor(options, simStatus.world)}</div>
        )}
        {simStatus?.headless && (
          <div className="status-line">Headless</div>
        )}
      </div>

      {/* Pursuit parameters (hidden while mission is active) */}
      {!flying && (
        <div className="script-config pursuit-config">
          <p className="script-description">
            Autonomous hangar circuit with live pigeon detection. On pigeon
            detection, pursues to deterrence range until deterrence, then
            resumes scanning.
          </p>

          <div className="script-args">
            <div className="form-label">Mission parameters</div>
            {PURSUIT_MISSION_ARGS.map((arg: ScriptArg) => (
              <ArgField
                key={arg.name}
                arg={arg}
                value={scriptArgValues[arg.name] as ScriptArgValues[string]}
                onChange={(v: ScriptArgValues[string]) => updateArg(arg.name, v)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="control-buttons">
        {!flying ? (
          <button className="btn btn-start" onClick={handleStart}>
            Start Patrol
          </button>
        ) : (
          <button className="btn btn-stop" onClick={onStopFlight}>
            Stop Patrol
          </button>
        )}
        <button className="btn btn-disconnect" onClick={onDisconnect} disabled={flying}>
          Disconnect
        </button>
      </div>

      {/* Panic reset — always available while connected (even mid-flight).
          Kills the flight, force-disarms, and teleports the drone to spawn. */}
      <button
        className="btn btn-panic"
        onClick={handleReset}
        disabled={resetting}
        title="Emergency: stop the flight, disarm, and snap the drone back to its spawn position."
      >
        {resetting ? 'RESETTING…' : '⟲ RESET DRONE'}
      </button>
      {resetMsg && <div className="panic-msg">{resetMsg}</div>}

      {flying && (
        <div className="flight-status">
          <div className="flight-timer">
            <span className="timer-label">Pursuit time</span>
            <span className="timer-value">{elapsed}</span>
          </div>
          <div className="flight-indicator">
            <span className="pulse"></span>
            Pursuit mission active
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

interface HudSelectOption {
  value: string;
  label: string;
}

function HudSelect({
  value,
  options,
  onChange,
  disabled = false,
}: {
  value: string;
  options: HudSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const listId = useId();
  const selected = options.find(option => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const selectOption = (next: string) => {
    onChange(next);
    setOpen(false);
  };

  return (
    <div className="hud-select" ref={rootRef}>
      <button
        type="button"
        className="hud-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => !disabled && setOpen(current => !current)}
      >
        <span>{selected?.label ?? ''}</span>
        <span className="hud-select-caret" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="hud-select-menu" id={listId} role="listbox">
          {options.map(option => (
            <button
              key={option.value}
              type="button"
              className={`hud-select-option ${option.value === value ? 'selected' : ''}`}
              role="option"
              aria-selected={option.value === value}
              onClick={() => selectOption(option.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  selectOption(option.value);
                }
              }}
            >
              <span>{option.label}</span>
              {option.value === value && <span className="hud-select-check" aria-hidden="true">✓</span>}
            </button>
          ))}
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
  const label = formatArgLabel(arg.flag || arg.name);

  if (arg.name === 'start_side') {
    const selected = value === 'right' ? 'right' : 'left';
    return (
      <div className="arg-field arg-start-side">
        <span className="arg-label">Initial Corner</span>
        <div className="start-side-options" role="radiogroup" aria-label="Initial corner">
          {(['left', 'right'] as const).map((side) => (
            <label key={side} className="start-side-option">
              <input
                type="checkbox"
                checked={selected === side}
                onChange={() => onChange(side)}
              />
              <span>{side === 'left' ? 'Left' : 'Right'}</span>
            </label>
          ))}
        </div>
        {arg.help && <span className="arg-help">{arg.help}</span>}
      </div>
    );
  }

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
