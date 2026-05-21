import React, { useState, useEffect, useCallback } from 'react';
import SimControl from '../components/SimControl';
import FlightHistory from '../components/FlightHistory';
import FlightModal from '../components/FlightModal';
import HudHeader from '../components/HudHeader';
import Sidebar from '../components/Sidebar';
import TelemetryRail from '../components/TelemetryRail';
import Minimap from '../components/Minimap';
import CameraStream from '../components/CameraStream';
import SystemLog from '../components/SystemLog';
import Ticker from '../components/Ticker';
import {
  Flight, SimStatus, FlightStatus, ConnectSimParams, StartFlightParams,
  SimOptions, WorldInfo,
} from '../types/flight';
import * as api from '../services/api';

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<'control' | 'history'>('control');
  const [simStatus, setSimStatus] = useState<SimStatus | null>(null);
  const [flightStatus, setFlightStatus] = useState<FlightStatus | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [selectedFlight, setSelectedFlight] = useState<Flight | null>(null);
  const [modalImages, setModalImages] = useState<string[]>([]);
  const [modalRecording, setModalRecording] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [flightStartTime, setFlightStartTime] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Sim options (worlds + cameras + scripts) — fetched once on mount so
  // CameraStream knows the available cameras for the active world.
  const [simOptions, setSimOptions] = useState<SimOptions | null>(null);
  useEffect(() => {
    api.getSimOptions().then(setSimOptions).catch(() => { });
  }, []);

  // Poll sim status. Fetch immediately on mount so the UI doesn't render a
  // stale "Offline" view for 3s after a page refresh while the sim is mid-launch.
  // On transient fetch errors, keep the last good state instead of nuking it
  // back to "Offline" — that previously bounced users to the pre-connect form
  // mid-launch on a single hiccup.
  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const status = await api.getSimStatus();
        if (!cancelled) setSimStatus(status);
      } catch {
        // ignore — keep last known state
      }
    };
    fetchOnce();
    const poll = setInterval(fetchOnce, 3000);
    return () => { cancelled = true; clearInterval(poll); };
  }, []);

  // Poll flight status when connected
  useEffect(() => {
    if (!simStatus?.connected) return;
    const poll = setInterval(async () => {
      try {
        const status = await api.getFlightStatus();
        setFlightStatus(status);
      } catch { }
    }, 2000);
    return () => clearInterval(poll);
  }, [simStatus?.connected]);

  // Fetch flights when switching to history
  useEffect(() => {
    if (activeTab === 'history') {
      api.getFlights().then(setFlights).catch(() => { });
    }
  }, [activeTab]);

  const handleConnect = useCallback(async (params: ConnectSimParams) => {
    setIsConnecting(true);
    setError(null);
    try {
      const result = await api.connectSim(params);
      if (!result.success) {
        setError(result.error || 'Failed to connect');
        setIsConnecting(false);
        return;
      }
      // Kick a sim/status fetch right away so we don't wait up to 3s for
      // the next regular poll to flip launching=true.
      try {
        const fresh = await api.getSimStatus();
        setSimStatus(fresh);
      } catch { /* the regular poller will catch up shortly */ }
      // Intentionally LEAVE isConnecting true. The button label would
      // otherwise flicker back to "Connect" for ~3s until the next
      // sim/status poll picks up launching=true. We clear isConnecting in
      // the effect below once we actually see launching or connected flip.
    } catch (e: any) {
      setError(e.message);
      setIsConnecting(false);
    }
  }, []);

  // Once the backend reports launching or connected, hand the spinner off
  // to the launch checklist / connected view; clear our local flag.
  useEffect(() => {
    if (isConnecting && (simStatus?.launching || simStatus?.connected)) {
      setIsConnecting(false);
    }
  }, [isConnecting, simStatus?.launching, simStatus?.connected]);

  const handleDisconnect = useCallback(async () => {
    try {
      await api.disconnectSim();
      setSimStatus({
        connected: false,
        launching: false,
        log: [],
        progress: { steps: [] },
        world: '',
        headless: false,
        camera: null,
        streamUrl: null,
      });
      setFlightStatus(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const handleStartFlight = useCallback(async (params: StartFlightParams) => {
    setError(null);
    try {
      const result = await api.startFlight(params);
      if (result.success) {
        setFlightStartTime(new Date());
      } else {
        setError('Failed to start detection');
      }
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const handleStopFlight = useCallback(async () => {
    try {
      await api.stopFlight();
      setFlightStartTime(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const handleSelectFlight = useCallback(async (flight: Flight) => {
    setSelectedFlight(flight);
    try {
      const [imgData, recData] = await Promise.all([
        api.getFlightImages(flight.id),
        api.getFlightRecording(flight.id),
      ]);
      setModalImages(imgData.images || []);
      setModalRecording(recData.recording || null);
    } catch {
      setModalImages([]);
      setModalRecording(null);
    }
  }, []);

  const connected = !!simStatus?.connected;
  const launching = !!simStatus?.launching;
  const flying = !!flightStatus?.isFlying;

  return (
    <div className="dashboard">
      <HudHeader
        connected={connected}
        launching={launching}
        flying={flying}
        world={simStatus?.world}
      />

      <Ticker connected={connected} flying={flying} />

      <TelemetryRail
        connected={connected}
        flying={flying}
      />

      <div className="dashboard-body">
        <Sidebar
          activeTab={activeTab}
          onChange={setActiveTab}
          connected={connected}
          flying={flying}
        />

        <main className="dashboard-main">
          {error && (
            <div className="error-message">{error}</div>
          )}

          {activeTab === 'control' && (
            <>
              <div className="control-grid">
                <SimControl
                  simStatus={simStatus}
                  flightStatus={flightStatus}
                  onConnect={handleConnect}
                  onDisconnect={handleDisconnect}
                  onStartFlight={handleStartFlight}
                  onStopFlight={handleStopFlight}
                  isConnecting={isConnecting}
                  flightStartTime={flightStartTime}
                />
                <div className="control-side-stack">
                  <Minimap active={connected} />
                  {simStatus?.headless && (
                    <CameraStream
                      streamUrl={simStatus.streamUrl}
                      launching={launching}
                      connected={connected}
                      camera={simStatus.camera}
                      availableCameras={
                        simOptions?.worlds.find(
                          (w: WorldInfo) => w.name === simStatus.world,
                        )?.cameras ?? []
                      }
                    />
                  )}
                </div>
              </div>
              <div className="lower-grid lower-grid-single">
                <SystemLog connected={connected} flying={flying} />
              </div>
            </>
          )}

          {activeTab === 'history' && (
            <FlightHistory
              flights={flights}
              onSelectFlight={handleSelectFlight}
            />
          )}
        </main>
      </div>

      {selectedFlight && (
        <FlightModal
          flight={selectedFlight}
          images={modalImages}
          recording={modalRecording}
          onClose={() => setSelectedFlight(null)}
        />
      )}
    </div>
  );
}
