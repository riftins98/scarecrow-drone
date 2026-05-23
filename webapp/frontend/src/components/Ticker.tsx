import React from 'react';

interface Props {
  connected: boolean;
  flying: boolean;
}

const FEED = [
  'SCARECROW UNIT-01',
  'GPS DENIED ENVIRONMENT',
  'LIDAR PRIMARY NAVIGATION',
  'OPTICAL FLOW SECONDARY',
  'EKF2 ATTITUDE ESTIMATOR',
  'PX4 v1.14',
  'MAVSDK TCP://14540',
  'YOLOV8 DETECTOR',
  'CLOSED LOOP CONTROL',
  'AUTONOMOUS DEPLOYMENT',
  'WALL FOLLOW ACTIVE',
  'PIGEON CLASS PRIMARY',
  'MISSION READY',
];

/**
 * Decorative scrolling tag strip between the header and telemetry rail.
 * No left state pill, no right rev tag — just the marquee.
 */
export default function Ticker({ connected, flying }: Props) {
  return (
    <div className={`ticker ${flying ? 'live' : connected ? 'nominal' : 'standby'}`}>
      <div className="ticker-track">
        <div className="ticker-stream">
          {FEED.concat(FEED).map((item, i) => (
            <span key={i} className="ticker-item">
              {item}
              <span className="ticker-sep">◆</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
