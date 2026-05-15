import React from 'react';
import Dashboard from './pages/Dashboard';
import './App.css';

function App() {
  return (
    <div className="App">
      <div className="hud-bg" aria-hidden="true">
        <div className="hud-grid" />
        <div className="hud-scanline" />
        <div className="hud-noise" />
        <div className="hud-vignette" />
        <svg className="hud-reticle hud-reticle-tl" viewBox="0 0 40 40" aria-hidden="true">
          <path d="M2 14 V2 H14" />
          <circle cx="2" cy="2" r="1.5" />
        </svg>
        <svg className="hud-reticle hud-reticle-tr" viewBox="0 0 40 40" aria-hidden="true">
          <path d="M38 14 V2 H26" />
          <circle cx="38" cy="2" r="1.5" />
        </svg>
        <svg className="hud-reticle hud-reticle-bl" viewBox="0 0 40 40" aria-hidden="true">
          <path d="M2 26 V38 H14" />
          <circle cx="2" cy="38" r="1.5" />
        </svg>
        <svg className="hud-reticle hud-reticle-br" viewBox="0 0 40 40" aria-hidden="true">
          <path d="M38 26 V38 H26" />
          <circle cx="38" cy="38" r="1.5" />
        </svg>
      </div>
      <Dashboard />
    </div>
  );
}

export default App;
