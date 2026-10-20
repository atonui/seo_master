import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { GoogleStatus, Owner, ReportDetail, ReportingSettings } from "./api/types";
import { ConnectionStatus } from "./components/ConnectionStatus";
import { SetupPage } from "./pages/SetupPage";
import { ReportPage } from "./pages/ReportPage";
import { ChatPanel } from "./pages/ChatPanel";
import { ConnectionsPage } from "./pages/ConnectionsPage";

type Page = "overview" | "reports" | "assistant" | "connections";

export default function App() {
  const [owner, setOwner] = useState<Owner | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [settings, setSettings] = useState<ReportingSettings | null>(null);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [page, setPage] = useState<Page>(window.location.hash.replace("#", "") as Page || "overview");

  const refreshConnections = useCallback(async () => {
    try {
      const status = await api.googleStatus(); setGoogle(status);
      const reporting = await api.settings(); setSettings(reporting);
    } catch (error) { setAuthError((error as Error).message); }
  }, []);

  useEffect(() => {
    api.me().then((account) => { setOwner(account); return refreshConnections(); })
      .catch((error: Error) => { setAuthError(error.message); })
      .finally(() => setAuthLoading(false));
  }, [refreshConnections]);
  useEffect(() => {
    const unauthorized = () => { setOwner(null); setGoogle(null); setSettings(null); };
    window.addEventListener("owner-unauthorized", unauthorized);
    return () => window.removeEventListener("owner-unauthorized", unauthorized);
  }, []);
  useEffect(() => { window.location.hash = page; }, [page]);

  async function login() {
    setAuthError("");
    try { window.location.assign((await api.connectGoogle()).authorization_url); }
    catch (error) { setAuthError((error as Error).message); }
  }
  if (authLoading) return <main className="auth-shell"><p>Checking private workspace…</p></main>;
  if (!owner) return <main className="auth-shell"><div className="auth-card"><div className="brand-mark">S</div><p className="eyebrow">SPARESTRACKER / GROWTH</p><h1>Your private marketing analyst.</h1><p>Sign in with the Google account configured as this workspace’s owner.</p>{authError && authError !== "Request failed (401)" && <p role="alert" className="error-box">{authError}</p>}<button className="button-primary" onClick={login}>Sign in with Google</button><small>Access is limited to one configured owner account.</small></div></main>;

  const nav: { key: Page; icon: string; label: string }[] = [{ key: "overview", icon: "◫", label: "Overview" }, { key: "reports", icon: "▤", label: "Reports" }, { key: "assistant", icon: "✳", label: "Ask the agent" }, { key: "connections", icon: "⤴", label: "Connections" }];
  return <main className="app-shell">
    <aside className="sidebar"><a className="brand" href="#overview" onClick={() => setPage("overview")} aria-label="Sparestracker Growth Desk home"><span className="brand-mark">S</span><span>sparestracker<span className="brand-muted"> / growth</span></span></a><p className="nav-label">WORKSPACE</p><nav aria-label="Main navigation">{nav.map((item) => <button key={item.key} className={`nav-link ${page === item.key ? "active" : ""}`} onClick={() => setPage(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="sidebar-bottom"><span className="private-dot" /> Private workspace<span className="owner-label">Only you can access this agent</span></div></aside>
    <section className="main-panel"><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {nav.find((item) => item.key === page)?.label}</div><div className="account"><ConnectionStatus status={google} /><span className="avatar">{owner.email[0]?.toUpperCase()}</span><span>{owner.email}</span></div></header>
      <div className="content">{page === "overview" && <SetupPage status={google} onRefresh={refreshConnections} onReport={() => setPage("reports")} />}{page === "reports" && <ReportPage onSelectReport={setReport} />}{page === "assistant" && <ChatPanel report={report} />}{page === "connections" && <ConnectionsPage status={google} settings={settings} onRefresh={refreshConnections} />}<footer>SPARESTRACKER GROWTH DESK <span>•</span> PRIVATE BY DESIGN</footer></div>
    </section>
  </main>;
}
