import React, { useEffect, useState } from 'react';
import { SimStatus, FlightStatus, SimOptions, SpawnPoint } from '../types/flight';
import * as api from '../services/api';
import SpawnPicker from './SpawnPicker';
import { spawnMapForWorld } from './spawnMapLookup';

interface Props {
  simStatus: SimStatus | null;
  flightStatus: FlightStatus | null;
  options: SimOptions | null;
}

/**
 * Standalone "Re-spawn" card: a top-down spawn picker + "Move Drone Here"
 * button that teleports the connected drone to a new start location without
 * relaunching the sim (also updates where the panic RESET returns to).
 *
 * Rendered as its own card to the LEFT of Sim Control (not nested inside it).
 * Only shown when the connected world has a spawn map and the drone is not
 * flying — teleporting a flight in progress is
 * unsafe, so the card hides itself during a flight.
 */
export default function RespawnPanel({ simStatus, flightStatus, options }: Props) {
  const connected = !!simStatus?.connected;
  const flying = !!flightStatus?.isFlying;

  const spawnMap = spawnMapForWorld(options, simStatus?.world);

  const [spawn, setSpawn] = useState<SpawnPoint | null>(null);
  const [respawning, setRespawning] = useState(false);
  const [respawnMsg, setRespawnMsg] = useState<string | null>(null);

  useEffect(() => {
    setSpawn(null);
  }, [simStatus?.world]);

  // Seed the marker from the live session spawn so the picker shows where the
  // drone currently is until the user picks somewhere else.
  useEffect(() => {
    if (connected && spawn === null && simStatus?.spawn) {
      setSpawn({ x: simStatus.spawn.x, y: simStatus.spawn.y });
    }
  }, [connected, simStatus, spawn]);

  const handleRespawn = async () => {
    if (!spawn || respawning) return;
    setRespawnMsg(null);
    setRespawning(true);
    try {
      const res = await api.setSpawn(spawn.x, spawn.y);
      setRespawnMsg(res.success
        ? `Drone moved to X ${spawn.x.toFixed(1)} Y ${spawn.y.toFixed(1)}.`
        : `Re-spawn failed: ${res.error || 'unknown error'}`);
    } catch (e) {
      setRespawnMsg(`Re-spawn failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRespawning(false);
      window.setTimeout(() => setRespawnMsg(null), 5000);
    }
  };

  // Nothing to show unless connected to a mapped world and on the ground.
  if (!connected || flying || !spawnMap) return null;

  return (
    <div className="drone-control respawn-card">
      <h2>Re-spawn</h2>
      <div className="respawn-panel respawn-panel-flush">
        <SpawnPicker
          map={spawnMap}
          value={spawn}
          onChange={setSpawn}
          disabled={respawning}
        />
        <button
          className="btn btn-respawn"
          onClick={handleRespawn}
          disabled={!spawn || respawning}
          title="Teleport the drone to the selected spot (also where RESET returns to)."
        >
          {respawning ? 'MOVING…' : 'Move Drone Here'}
        </button>
        {respawnMsg && <div className="panic-msg">{respawnMsg}</div>}
      </div>
    </div>
  );
}
