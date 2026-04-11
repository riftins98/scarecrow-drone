import React, { useState, useEffect, useCallback } from 'react';
import SimControl from '../components/SimControl';
import FlightHistory from '../components/FlightHistory';
import FlightModal from '../components/FlightModal';
import { Flight, SimStatus, FlightStatus } from '../types/flight';
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

  // Poll sim status
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const status = await api.getSimStatus();
        setSimStatus(status);
      } catch {
        setSimStatus({ connected: false, launching: false, log: [], progress: { steps: [] } });
      }
    }, 3000);
    return () => clearInterval(poll);
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

  const handleConnect = useCallback(async () => {
    setIsConnecting(true);
    setError(null);
    try {
      const result = await api.connectSim();
      if (!result.success) setError(result.error || 'Failed to connect');
    } catch (e: any) {
      setError(e.message);
    }
    setIsConnecting(false);
  }, []);

  const handleDisconnect = useCallback(async () => {
    try {
      await api.disconnectSim();
      setSimStatus({ connected: false, launching: false, log: [], progress: { steps: [] } });
      setFlightStatus(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const handleStartFlight = useCallback(async () => {
    setError(null);
    try {
      const result = await api.startFlight();
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

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Scarecrow Drone</h1>
        <p>GPS-Denied Pigeon Detection Simulation</p>
      </div>

      <div className="dashboard-nav">
        <button
          className={`nav-btn ${activeTab === 'control' ? 'active' : ''}`}
          onClick={() => setActiveTab('control')}
        >Drone Control</button>
        <button
          className={`nav-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >Detection History</button>
      </div>

      {error && (
        <div className="error-message">{error}</div>
      )}

      {activeTab === 'control' && (
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
      )}

      {activeTab === 'history' && (
        <FlightHistory
          flights={flights}
          onSelectFlight={handleSelectFlight}
        />
      )}

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
