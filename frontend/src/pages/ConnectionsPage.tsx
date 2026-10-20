import { api } from "../api/client";
import type { GoogleStatus, ReportingSettings } from "../api/types";
import { ConnectionStatus } from "../components/ConnectionStatus";

export function ConnectionsPage({ status, settings, onRefresh }: { status: GoogleStatus | null; settings: ReportingSettings | null; onRefresh: () => void }) {
  async function disconnect() {
    if (!window.confirm("Disconnect Google and delete saved reports from this workspace?")) return;
    await api.disconnectGoogle();
    onRefresh();
  }
  return <div className="page-stack"><div className="page-title"><div><p className="eyebrow">SOURCES</p><h1>Your connections.</h1><p>Read-only access is used to build reports. You can disconnect at any time.</p></div><ConnectionStatus status={status} /></div>
    <section className="panel connection-row"><div><h2>Google Analytics and Search Console</h2><p>Selected Search Console property: {settings?.search_console_site ?? "None"}</p><p>Selected GA4 property: {settings?.ga4_property_id ?? "None"}</p></div><ConnectionStatus status={status} />{status?.connected && <button className="button-danger" onClick={disconnect}>Disconnect and delete reports</button>}</section>
    <section className="panel"><h2>Website audit</h2><p>{settings?.site_url ? `Configured domain: ${settings.site_url}` : "Set your website origin in Setup to enable a safe technical audit."}</p></section>
  </div>;
}
