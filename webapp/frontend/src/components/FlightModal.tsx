import React from 'react';
import { Flight } from '../types/flight';
import { detectionImageUrl, recordingUrl } from '../services/api';

interface Props {
  flight: Flight;
  images: string[];
  recording: string | null;
  onClose: () => void;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export default function FlightModal({ flight, images, recording, onClose }: Props) {
  const [tab, setTab] = React.useState<'summary' | 'detections' | 'recording'>('summary');
  const [selectedImage, setSelectedImage] = React.useState<string | null>(null);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
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
            >Detections ({images.length})</button>
            <button
              className={`modal-tab ${tab === 'recording' ? 'active' : ''}`}
              onClick={() => setTab('recording')}
            >Recording</button>
          </div>
        </div>

        <div className="modal-content">
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
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
                  gap: 10
                }}>
                  {images.map((img, i) => {
                    const filename = img.split('/').pop() || img;
                    const url = detectionImageUrl(flight.id, filename);
                    return (
                      <img
                        key={i}
                        src={url}
                        alt={`Detection ${i + 1}`}
                        style={{
                          width: '100%', borderRadius: 4, cursor: 'pointer',
                          border: '1px solid #3a3a3a'
                        }}
                        onClick={() => setSelectedImage(url)}
                      />
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

          {tab === 'recording' && (
            <div className="modal-video-container">
              {recording ? (
                <video
                  className="flight-video-player"
                  controls
                  src={recordingUrl(flight.id, recording.split('/').pop() || '')}
                />
              ) : (
                <p>No recording available</p>
              )}
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
