export interface Flight {
  id: string;
  date: string;
  startTime: string;
  endTime?: string;
  duration: number;
  pigeonsDetected: number;
  framesProcessed: number;
  status: 'completed' | 'in_progress' | 'failed';
  videoPath?: string;
}

export interface LaunchStep {
  id: string;
  label: string;
  status: 'done' | 'active' | 'pending';
  /** Live progress text for the active step (e.g. "Compiling [847/1157] foo.cpp"). */
  substatus?: string;
}

export interface SimStatus {
  connected: boolean;
  launching: boolean;
  log: string[];
  progress: { steps: LaunchStep[] };
  world: string;
  headless: boolean;
  /** Camera flag stem currently streamed (e.g. "fixed"), null in GUI mode. */
  camera: string | null;
  streamUrl: string | null;
}

export interface FlightStatus {
  isFlying: boolean;
  isConnected: boolean;
  running: boolean;
  flight_id: string | null;
  pigeons_detected: number;
  frames_processed: number;
  /** Latest TELEMETRY: payload from the flight script, enriched by the
   *  backend log parser. Empty {} before the first emission. Which fields
   *  are present depends on the running script (the rail hides the rest). */
  telemetry?: {
    battery?: number;        // percent 0..100
    distance?: number;       // meters from takeoff
    detections?: number;     // cumulative pigeon hits
    altitude?: number;       // meters AGL (demo flights)
    heading?: number;        // degrees -180..180
    // --- Parsed from human log lines by the backend (DetectionService) ---
    phase?: string;          // short uppercase phase label, e.g. "HOVER"
    agl?: number;            // live altitude-above-ground during climb/descent
    ceiling?: number;        // ceiling clearance, meters (ceiling scripts)
    leg?: number;            // room-circuit leg number
    // Lidar wall distances in meters; null means "no wall on that side" (inf).
    front?: number | null;
    left?: number | null;
    right?: number | null;
    rear?: number | null;
    wall?: number | null;    // active-side distance in the wall-follow controllers
    // Commanded velocities from the control loop.
    fwd?: number;            // forward m/s
    lat?: number;            // lateral m/s
    yaw?: number;            // yaw deg/s
    // Mission outcomes.
    target?: string;         // pursuit: "REACHED" or an uppercase exit reason
    target_dist?: number;    // pursuit: front distance at target, meters
    stop_reason?: string;    // wall-follow terminal stop reason (uppercase)
    fps?: number;            // detection throughput (detect_pigeons summary)
  };
}

// --- Sim options (worlds + scripts available for the user to pick) ---

export interface CameraInfo {
  /** Launcher flag stem, e.g. "fixed". Sent back in ConnectSimParams.camera. */
  name: string;
  /** Pretty label for the dropdown. */
  label: string;
  /** Underlying SDF model used (mono_cam_hd / mono_cam). Not shown in UI. */
  model: string;
}

export interface WorldInfo {
  name: string;
  path: string;
  cameras: CameraInfo[];
}

export interface ScriptArg {
  name: string;            // python identifier (underscores)
  flag: string;            // "--target-alt"
  type: 'str' | 'int' | 'float' | 'bool' | 'choice';
  default: string | number | boolean | null;
  help: string;
  choices?: string[] | null;
  required?: boolean;
}

export interface ScriptInfo {
  name: string;            // filename
  path: string;
  description: string;
  args: ScriptArg[];
  parse_error?: string | null;
}

export interface SimOptions {
  worlds: WorldInfo[];
  scripts: ScriptInfo[];
}

export interface ConnectSimParams {
  world?: string;
  headless?: boolean;
  /** Headless-only. Picks which streamable camera the launcher points the
   *  WebRTC stream at. Backend silently falls back to "fixed" if invalid. */
  camera?: string;
}

// Map of {arg_name: value} sent to /api/flight/start.
export type ScriptArgValues = Record<string, string | number | boolean | null>;

export interface StartFlightParams {
  script?: string;
  args?: ScriptArgValues;
}
