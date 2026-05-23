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
  /** Gazebo real_time_factor (0..1+). null before the poller has a reading. */
  rtf: number | null;
}

export interface FlightStatus {
  isFlying: boolean;
  isConnected: boolean;
  running: boolean;
  flight_id: string | null;
  pigeons_detected: number;
  frames_processed: number;
  /** Latest TELEMETRY: payload from the flight script. Empty {} before
   *  the first emission. Fields below are present once the script runs. */
  telemetry?: {
    battery?: number;        // percent 0..100
    distance?: number;       // meters
    detections?: number;     // cumulative pigeon hits
    altitude?: number;       // meters AGL
    heading?: number;        // degrees -180..180
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
