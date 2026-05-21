import React from 'react';

interface Props {
  activeTab: 'control' | 'history';
  onChange: (tab: 'control' | 'history') => void;
  connected: boolean;
  flying: boolean;
}

export default function Sidebar({ activeTab, onChange, connected, flying }: Props) {
  return (
    <nav className="hud-sidebar" aria-label="Primary">
      <div className="hud-sidebar-section">
        <div className="hud-sidebar-section-label">OPS</div>
        <SidebarBtn
          active={activeTab === 'control'}
          icon={<IconControl />}
          label="Control"
          sub={connected ? (flying ? 'flying' : 'online') : 'offline'}
          onClick={() => onChange('control')}
        />
        <SidebarBtn
          active={activeTab === 'history'}
          icon={<IconHistory />}
          label="History"
          sub="log"
          onClick={() => onChange('history')}
        />
      </div>

      <div className="hud-sidebar-section">
        <div className="hud-sidebar-section-label">DIAGNOSTICS</div>
        <SidebarBtn
          active={false}
          disabled
          icon={<IconLayers />}
          label="World Map"
          sub="work in progress"
        />
        <SidebarBtn
          active={false}
          disabled
          icon={<IconGear />}
          label="Settings"
          sub="work in progress"
        />
      </div>
    </nav>
  );
}

function SidebarBtn({
  active, disabled, icon, label, sub, onClick,
}: {
  active: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  label: string;
  sub: string;
  onClick?: () => void;
}) {
  return (
    <button
      className={`hud-sidebar-btn ${active ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={onClick}
      disabled={disabled}
      type="button"
    >
      <span className="hud-sidebar-icon" aria-hidden="true">{icon}</span>
      <span className="hud-sidebar-text">
        <span className="hud-sidebar-label">{label}</span>
        <span className="hud-sidebar-sub">{sub}</span>
      </span>
      {active && <span className="hud-sidebar-marker" aria-hidden="true" />}
    </button>
  );
}

const stroke = { stroke: 'currentColor', strokeWidth: 1.6, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

function IconControl() {
  return (
    <svg viewBox="0 0 20 20" {...stroke}>
      <path d="M10 2 L10 6 M10 14 L10 18 M2 10 L6 10 M14 10 L18 10" />
      <circle cx="10" cy="10" r="3" />
    </svg>
  );
}
function IconHistory() {
  return (
    <svg viewBox="0 0 20 20" {...stroke}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6 L10 10 L13 12" />
    </svg>
  );
}
function IconLayers() {
  return (
    <svg viewBox="0 0 20 20" {...stroke}>
      <path d="M10 3 L17 7 L10 11 L3 7 Z" />
      <path d="M3 12 L10 16 L17 12" />
    </svg>
  );
}
function IconGear() {
  return (
    <svg viewBox="0 0 20 20" {...stroke}>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2 L10 4 M10 16 L10 18 M2 10 L4 10 M16 10 L18 10 M4 4 L5.5 5.5 M14.5 14.5 L16 16 M4 16 L5.5 14.5 M14.5 5.5 L16 4" />
    </svg>
  );
}
