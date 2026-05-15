import React, { useEffect, useState } from 'react';

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

export default function Ticker({ connected, flying }: Props) {
  const [tag, setTag] = useState<string>('STANDBY');
  useEffect(() => {
    if (flying) setTag('MISSION ACTIVE');
    else if (connected) setTag('SYSTEMS NOMINAL');
    else setTag('STANDBY');
  }, [connected, flying]);

  return (
    <div className={`ticker ${flying ? 'live' : connected ? 'nominal' : 'standby'}`}>
      <div className="ticker-tag">
        <span className="ticker-tag-bullet" /> {tag}
      </div>
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
      <div className="ticker-end">REV 26.05</div>
    </div>
  );
}
