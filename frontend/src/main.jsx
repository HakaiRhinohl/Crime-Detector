import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Bell, Crosshair, ExternalLink, RefreshCw, Search, Signal } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [tab, setTab] = useState("alerts");
  const [alerts, setAlerts] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [assetSymbol, setAssetSymbol] = useState("WIF");
  const [asset, setAsset] = useState(null);
  const [loading, setLoading] = useState(false);

  async function loadLists() {
    setLoading(true);
    try {
      const [alertsRes, candidatesRes] = await Promise.all([
        fetch(`${API_BASE}/alerts?limit=100`),
        fetch(`${API_BASE}/candidates?limit=100`),
      ]);
      setAlerts(alertsRes.ok ? await alertsRes.json() : []);
      setCandidates(candidatesRes.ok ? await candidatesRes.json() : []);
    } finally {
      setLoading(false);
    }
  }

  async function loadAsset(symbol = assetSymbol) {
    if (!symbol.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/asset/${symbol.trim().toUpperCase()}`);
      setAsset(res.ok ? await res.json() : null);
      setTab("asset");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLists();
  }, []);

  const activeRows = tab === "alerts" ? alerts : candidates;

  return (
    <main>
      <aside>
        <div className="brand">
          <Signal size={24} />
          <span>Structure Scanner</span>
        </div>
        <button className={tab === "alerts" ? "active" : ""} onClick={() => setTab("alerts")}>
          <Bell size={18} />
          <span>Alerts</span>
        </button>
        <button className={tab === "candidates" ? "active" : ""} onClick={() => setTab("candidates")}>
          <Activity size={18} />
          <span>Candidates</span>
        </button>
        <button className={tab === "asset" ? "active" : ""} onClick={() => setTab("asset")}>
          <Crosshair size={18} />
          <span>Asset</span>
        </button>
      </aside>

      <section className="workspace">
        <header>
          <div>
            <h1>{tab === "asset" ? asset?.asset?.symbol || "Asset" : tab === "alerts" ? "Alerts" : "Candidates"}</h1>
            <p>{new Date().toLocaleString()}</p>
          </div>
          <div className="actions">
            <label className="search">
              <Search size={16} />
              <input value={assetSymbol} onChange={(event) => setAssetSymbol(event.target.value)} onKeyDown={(event) => event.key === "Enter" && loadAsset()} />
            </label>
            <button title="Open asset" onClick={() => loadAsset()}>
              <Crosshair size={18} />
            </button>
            <button title="Refresh" onClick={loadLists}>
              <RefreshCw size={18} className={loading ? "spin" : ""} />
            </button>
          </div>
        </header>

        {tab === "asset" ? <AssetView asset={asset} /> : <AlertTable rows={activeRows} />}
      </section>
    </main>
  );
}

function AlertTable({ rows }) {
  if (!rows.length) {
    return <div className="empty">No rows yet.</div>;
  }
  return (
    <div className="table">
      <div className="thead">
        <span>Time</span>
        <span>Token</span>
        <span>Detector</span>
        <span>Severity</span>
        <span>Telegram</span>
        <span>Event</span>
      </div>
      {rows.map((row) => (
        <div className="tr" key={row.id}>
          <span>{formatTime(row.ts)}</span>
          <strong>{row.symbol}</strong>
          <span>{row.detector}</span>
          <Severity value={row.severity} />
          <span>{row.telegram_sent ? "sent" : "stored"}</span>
          <span>{row.message}</span>
        </div>
      ))}
    </div>
  );
}

function AssetView({ asset }) {
  const latest = useMemo(() => {
    if (!asset?.market?.length) return null;
    return asset.market[asset.market.length - 1];
  }, [asset]);

  if (!asset) {
    return <div className="empty">No asset loaded.</div>;
  }

  return (
    <div className="asset">
      <div className="metrics">
        <Metric label="Price" value={latest?.price ? `$${fmt(latest.price)}` : "n/a"} />
        <Metric label="OI" value={latest?.open_interest_usd ? `$${fmt(latest.open_interest_usd)}` : "n/a"} />
        <Metric label="Spot" value={(asset.coverage.spot_venues || []).join(", ") || "None"} />
        <Metric label="Perp" value={(asset.coverage.perp_venues || []).join(", ") || "None"} />
      </div>

      <div className="columns">
        <Panel title="Market">
          {asset.market.slice(-80).map((row, index) => (
            <Row key={`${row.ts}-${index}`} left={`${row.venue} ${row.market_type}`} mid={formatTime(row.ts)} right={row.price ? `$${fmt(row.price)}` : "n/a"} />
          ))}
        </Panel>
        <Panel title="Depth">
          {asset.orderbooks.slice(-80).map((row, index) => (
            <Row key={`${row.ts}-${index}`} left={`${row.venue} ${row.market_type}`} mid={`${fmt(row.spread_bps || 0)} bps`} right={`$${fmt(row.depth_100bps_usd || 0)}`} />
          ))}
        </Panel>
      </div>

      <div className="columns">
        <Panel title="DEX">
          {asset.dex.slice(-40).map((row, index) => (
            <Row key={`${row.ts}-${index}`} left={row.dex_id || row.chain} mid={`$${fmt(row.liquidity_usd || 0)}`} right={row.dexscreener_url ? <a href={row.dexscreener_url} target="_blank"><ExternalLink size={14} /></a> : "n/a"} />
          ))}
        </Panel>
        <Panel title="Alerts">
          {asset.alerts.map((row, index) => (
            <Row key={`${row.ts}-${index}`} left={row.detector} mid={<Severity value={row.severity} />} right={formatTime(row.ts)} />
          ))}
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <div>{children}</div>
    </section>
  );
}

function Row({ left, mid, right }) {
  return (
    <div className="row">
      <span>{left}</span>
      <span>{mid}</span>
      <strong>{right}</strong>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Severity({ value }) {
  return <span className={`severity ${value}`}>{value}</span>;
}

function formatTime(ts) {
  return ts ? new Date(ts).toLocaleString() : "n/a";
}

function fmt(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return Intl.NumberFormat("en", { maximumFractionDigits: value > 100 ? 0 : 4 }).format(value);
}

createRoot(document.getElementById("root")).render(<App />);

