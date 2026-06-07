import React from 'react';
import { Flight } from '../types/flight';
import { detectionImageUrl, missionMapUrl } from '../services/api';

interface Props {
  flight: Flight;
  images: string[];
  onClose: () => void;
}

type DetectionPhase = 'trigger' | 'start' | 'centered' | 'reached' | 'unknown';

interface DetectionImage {
  src: string;
  filename: string;
  leg: number | null;
  pursuit: number | null;
  attempt: number | null;
  phase: DetectionPhase;
  frame: number | null;
}

const PHASE_ORDER: DetectionPhase[] = ['trigger', 'start', 'centered', 'reached', 'unknown'];

const PHASE_LABELS: Record<DetectionPhase, string> = {
  trigger: 'Detected',
  start: 'Pursuit Start',
  centered: 'Target Centered',
  reached: 'Target Reached',
  unknown: 'Detection',
};

const PHASE_HINTS: Record<DetectionPhase, string> = {
  trigger: 'Wall-follow camera found a pigeon candidate.',
  start: 'Drone switched from scan mode into pursuit.',
  centered: 'Target was centered enough for final approach.',
  reached: 'Drone reached the configured target distance.',
  unknown: 'Captured detection image.',
};

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function parseDetectionImage(flightId: string, imagePath: string): DetectionImage {
  const filename = imagePath.split('/').pop() || imagePath;
  const url = detectionImageUrl(flightId, filename);
  const match = filename.match(
    /leg[_-]?(\d+)[_-]pursuit[_-]?(\d+)[_-](?:attempt|attermpt)[_-]?(\d+)[_-](trigger|start|centered|reached)[_-](\d+)\.png$/i
  );

  if (!match) {
    return {
      src: url,
      filename,
      leg: null,
      pursuit: null,
      attempt: null,
      phase: 'unknown',
      frame: null,
    };
  }

  return {
    src: url,
    filename,
    leg: Number(match[1]),
    pursuit: Number(match[2]),
    attempt: Number(match[3]),
    phase: match[4].toLowerCase() as DetectionPhase,
    frame: Number(match[5]),
  };
}

function groupDetectionImages(images: DetectionImage[]) {
  const groups = new Map<string, DetectionImage[]>();
  for (const img of images) {
    const key = img.leg && img.pursuit && img.attempt
      ? `leg-${img.leg}-pursuit-${img.pursuit}-attempt-${img.attempt}`
      : `unknown-${img.filename}`;
    groups.set(key, [...(groups.get(key) || []), img]);
  }

  return Array.from(groups.values())
    .map((group) => group.sort((a, b) => {
      const phaseDelta = PHASE_ORDER.indexOf(a.phase) - PHASE_ORDER.indexOf(b.phase);
      if (phaseDelta !== 0) return phaseDelta;
      return (a.frame || 0) - (b.frame || 0);
    }))
    .sort((a, b) => {
      const firstA = a[0];
      const firstB = b[0];
      return (firstA.pursuit || 999) - (firstB.pursuit || 999)
        || (firstA.leg || 999) - (firstB.leg || 999)
        || (firstA.attempt || 999) - (firstB.attempt || 999);
    });
}

export default function FlightModal({ flight, images, onClose }: Props) {
  const [tab, setTab] = React.useState<'summary' | 'detections' | 'map'>('summary');
  const [selectedImage, setSelectedImage] = React.useState<string | null>(null);
  const detectionGroups = React.useMemo(
    () => groupDetectionImages(images.map((img) => parseDetectionImage(flight.id, img))),
    [flight.id, images]
  );
  const pursuitFlowCount = flight.pursuitFlowCount || detectionGroups.length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal modal-${tab}`} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Detection Session — {flight.id}</h3>
          <div className="modal-tabs">
            <button
              className={`modal-tab ${tab === 'summary' ? 'active' : ''}`}
              onClick={() => setTab('summary')}
            >Summary</button>
            <button
              className={`modal-tab ${tab === 'detections' ? 'active' : ''}`}
              onClick={() => setTab('detections')}
            >Detections</button>
            {flight.mapPath && (
              <button
                className={`modal-tab ${tab === 'map' ? 'active' : ''}`}
                onClick={() => setTab('map')}
              >Mission Map</button>
            )}
          </div>
        </div>

        <div className={`modal-content modal-content-${tab}`}>
          {tab === 'summary' && (
            <div className="flight-summary">
              <div className="summary-row">
                <span className="label">Status</span>
                <span className="value">{flight.status.replace('_', ' ').toUpperCase()}</span>
              </div>
              <div className="summary-row">
                <span className="label">Date</span>
                <span className="value">{new Date(flight.startTime).toLocaleString()}</span>
              </div>
              <div className="summary-row">
                <span className="label">Duration</span>
                <span className="value">{formatDuration(flight.duration)}</span>
              </div>
              <div className="summary-row">
                <span className="label">Pigeons Detected</span>
                <span className="value" style={{ color: '#8b9a5b' }}>{flight.pigeonsDetected}</span>
              </div>
              <div className="summary-row">
                <span className="label">Pigeons Deterred</span>
                <span className="value" style={{ color: '#8b9a5b' }}>{flight.pigeonsDeterred || 0}</span>
              </div>
              <div className="summary-row">
                <span className="label">Pursuit Flows</span>
                <span className="value">{pursuitFlowCount} FLOWS · {images.length} IMAGES</span>
              </div>
              <div className="summary-row">
                <span className="label">Frames Processed</span>
                <span className="value">{flight.framesProcessed}</span>
              </div>
            </div>
          )}

          {tab === 'detections' && (
            <div className="modal-images-container">
              {images.length === 0 ? (
                <p>No detection images captured</p>
              ) : (
                <div className="detection-flow-list">
                  {detectionGroups.map((group, groupIndex) => {
                    const first = group[0];
                    const title = first.leg && first.pursuit && first.attempt
                      ? `Pursuit ${String(first.pursuit).padStart(2, '0')} : Leg ${first.leg} : Attempt ${first.attempt}`
                      : `Detection ${groupIndex + 1}`;
                    return (
                      <section className="detection-flow-card" key={`${title}-${groupIndex}`}>
                        <div className="detection-flow-header">
                          <span className="detection-flow-title">{title}</span>
                        </div>
                        <div className="detection-phase-grid">
                          {group.map((img) => (
                            <button
                              className={`detection-phase-card phase-${img.phase}`}
                              key={img.filename}
                              onClick={() => setSelectedImage(img.src)}
                              aria-label={`${PHASE_LABELS[img.phase]} image, ${title}`}
                            >
                              <div className="detection-phase-image-wrap">
                                <img
                                  src={img.src}
                                  alt={`${PHASE_LABELS[img.phase]} for ${title}`}
                                  className="detection-phase-image"
                                />
                              </div>
                              <div className="detection-phase-meta">
                                <span className="detection-phase-label">{PHASE_LABELS[img.phase]}</span>
                                <span className="detection-phase-hint">{PHASE_HINTS[img.phase]}</span>
                                {img.frame !== null && (
                                  <span className="detection-phase-frame">FRAME {String(img.frame).padStart(4, '0')}</span>
                                )}
                              </div>
                            </button>
                          ))}
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}
              {selectedImage && (
                <div className="modal-overlay" onClick={() => setSelectedImage(null)}
                  style={{ zIndex: 2000 }}>
                  <img src={selectedImage} alt="Detection"
                    style={{ maxWidth: '90%', maxHeight: '90%', borderRadius: 4 }}
                    onClick={e => e.stopPropagation()} />
                </div>
              )}
            </div>
          )}

          {tab === 'map' && flight.mapPath && (
            <div className="modal-map-container">
              <img
                src={missionMapUrl(flight.id, flight.mapPath.split('/').pop() || 'map_annotated.png')}
                alt="Mission map"
                className="mission-map-image"
                style={{
                  width: '100%',
                  borderRadius: 4,
                  cursor: 'pointer',
                  border: '1px solid #3a3a3a',
                }}
                onClick={() => setSelectedImage(
                  missionMapUrl(flight.id, flight.mapPath!.split('/').pop() || 'map_annotated.png')
                )}
              />
            </div>
          )}
        </div>

        <button className="btn btn-disconnect modal-close-btn" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
