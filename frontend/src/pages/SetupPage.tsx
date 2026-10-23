import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { GoogleStatus, PropertyList, ReportingSettings } from "../api/types";
import { ConnectionStatus } from "../components/ConnectionStatus";

export function SetupPage({ status, onRefresh, onReport }: { status: GoogleStatus | null; onRefresh: () => void; onReport: () => void }) {
  const [properties, setProperties] = useState<PropertyList | null>(null);
  const [settings, setSettings] = useState<ReportingSettings>({ site_url: "", search_console_site: "", ga4_property_id: "", cta_event: "", invite_submit_event: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const connectInProgress = useRef(false);
  useEffect(() => {
    if (!status?.connected) return;
    Promise.all([api.properties(), api.settings()]).then(([list, current]) => { setProperties(list); setSettings(current); }).catch((e: Error) => setError(e.message));
  }, [status?.connected]);
  const edit = (key: keyof ReportingSettings, value: string) => setSettings((current) => ({ ...current, [key]: value || null }));
  async function connect() {
    if (connectInProgress.current) return;
    connectInProgress.current = true;
    setBusy(true); setError("");
    try { window.location.assign((await api.connectGoogle()).authorization_url); }
    catch (e) { setError((e as Error).message); setBusy(false); connectInProgress.current = false; }
  }
  async function save() {
    setBusy(true); setError(""); setSaved(false);
    try { setSettings(await api.saveSettings(settings)); setSaved(true); onRefresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="page-stack" id="setup-page">
    <div className="page-title"><div><p className="eyebrow">SETUP</p><h1>Connect your sources.</h1><p>Read-only access. Reports and suggestions stay inside this private workspace.</p></div><ConnectionStatus status={status} /></div>
    <section className="panel"><h2>Google Analytics and Search Console</h2><p>Authorize the Google account that owns your Sparestracker reports.</p>
      <div className="inline-row"><ConnectionStatus status={status} />{!status?.connected || status.reconnect_required ? <button className="button-primary" onClick={connect} disabled={busy}>{status?.reconnect_required ? "Reconnect Google" : "Connect Google"}</button> : <span className="quiet">Connected to your owner account</span>}</div>
    </section>
    {status?.connected && <section className="panel"><h2>Choose report sources</h2>
      <label>Website origin<input value={settings.site_url ?? ""} placeholder="https://sparestracker.com" onChange={(e) => edit("site_url", e.target.value)} /></label>
      <label>Search Console property<select value={settings.search_console_site ?? ""} onChange={(e) => edit("search_console_site", e.target.value)}><option value="">Not selected</option>{properties?.search_console.map((item) => <option key={item.site_url} value={item.site_url}>{item.site_url}</option>)}</select></label>
      <label>GA4 property<select value={settings.ga4_property_id ?? ""} onChange={(e) => edit("ga4_property_id", e.target.value)}><option value="">Not selected</option>{properties?.ga4.map((item) => <option key={item.property_id} value={item.property_id}>{item.display_name} · {item.property_id}</option>)}</select></label>
      <div className="form-grid"><label>CTA event name<input value={settings.cta_event ?? ""} placeholder="e.g. cta_click" onChange={(e) => edit("cta_event", e.target.value)} /></label><label>Invitation submission event<input value={settings.invite_submit_event ?? ""} placeholder="e.g. invite_submit" onChange={(e) => edit("invite_submit_event", e.target.value)} /></label></div>
      <p className="quiet">Until the invitation event is mapped, the agent will show tracking setup as incomplete instead of reporting zero conversions.</p>
      {properties?.warnings.map((warning) => <p className="inline-warning" key={warning}>{warning}</p>)}
      {saved && <p role="status" className="success">Settings saved.</p>}
      <div className="button-row"><button className="button-primary" onClick={save} disabled={busy}>Save settings</button><button className="button-secondary" onClick={onReport}>Open reports</button></div>
    </section>}
    {error && <p role="alert" className="error-box">{error}</p>}
  </div>;
}
