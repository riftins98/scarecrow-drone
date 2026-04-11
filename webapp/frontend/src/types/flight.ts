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
}

export interface SimStatus {
  connected: boolean;
  launching: boolean;
  log: string[];
  progress: { steps: LaunchStep[] };
}

export interface FlightStatus {
  isFlying: boolean;
  isConnected: boolean;
  running: boolean;
  flight_id: string | null;
  pigeons_detected: number;
  frames_processed: number;
}
