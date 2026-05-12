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
  streamUrl: string | null;
}

export interface FlightStatus {
  isFlying: boolean;
  isConnected: boolean;
  running: boolean;
  flight_id: string | null;
  pigeons_detected: number;
  frames_processed: number;
}

// --- Sim options (worlds + scripts available for the user to pick) ---

export interface WorldInfo {
  name: string;
  path: string;
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
}

// Map of {arg_name: value} sent to /api/flight/start.
export type ScriptArgValues = Record<string, string | number | boolean | null>;

export interface StartFlightParams {
  script?: string;
  args?: ScriptArgValues;
}
