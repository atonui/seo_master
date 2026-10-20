import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReportDetail, ReportSummary } from "../api/types";
import { MetricEvidence } from "../components/MetricEvidence";

function stale(createdAt: string) { return Date.now() - new Date(createdAt).getTime() > 7 * 24 * 60 * 60 * 1000; }

export function ReportPage({ onSelectReport }: { onSelectReport: (report: ReportDetail | null) => void }) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  async function refresh(selectedId?: string) {
    setLoading(true); setError("");
    try {
      const items = await api.reports(); setReports(items);
      const selected = items.find((item) => item.id === selectedId) ?? items[0];
      const detail = selected ? await api.report(selected.id) : null;
      setReport(detail); onSelectReport(detail);
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function run() {
    setRunning(true); setError("");
    try { const result = await api.runReport(); setReports((items) => [result, ...items.filter((item) => item.id !== result.id)]); setReport(result); onSelectReport(result); }
    catch (e) { setError((e as Error).message); }
    finally { setRunning(false); }
  }
  async function remove() {
    if (!report || !window.confirm("Delete this saved report?")) return;
    await api.deleteReport(report.id); await refresh();
  }
  return <div className="page-stack" id="report-page"><div className="page-title"><div><p className="eyebrow">PERFORMANCE</p><h1>Your reports.</h1><p>Recommendations link to the source values they use.</p></div><button className="button-primary" onClick={run} disabled={running}>{running ? "Running report…" : "Run report"}</button></div>
    {error && <p role="alert" className="error-box">{error}</p>}
    {loading ? <p className="panel">Loading reports…</p> : reports.length === 0 ? <section className="panel empty-state"><h2>No reports yet</h2><p>Run a report after choosing at least one source in Setup.</p></section> : <div className="report-layout">
      <aside className="panel report-history"><h2>Saved reports</h2>{reports.map((item) => <button key={item.id} className={`history-item ${item.id === report?.id ? "selected" : ""}`} onClick={() => void refresh(item.id)}><strong>{item.date_range}</strong><span>{new Date(item.created_at).toLocaleString()} · {item.finding_count} findings</span></button>)}</aside>
      {report && <article className="report-content">
        {stale(report.created_at) && <p role="status" className="inline-warning">This report is over seven days old. Run a fresh report before acting on it.</p>}
        {report.status === "partial" && <p role="status" className="inline-warning">Some source data was incomplete. Treat these findings as partial. {report.warning}</p>}
        {report.funnel?.status === "setup_needed" && <p role="status" className="inline-warning">{report.funnel.warning ?? "Map the invitation event to measure conversions."}</p>}
        {report.funnel?.status === "incomplete" && <p role="status" className="inline-warning">{report.funnel.warning}</p>}
        <section className="panel"><div className="report-heading"><div><p className="eyebrow">REPORT WINDOW</p><h2>{report.date_range}</h2></div><button className="button-danger" onClick={remove}>Delete report</button></div>
          <div className="metric-grid">{report.comparison.map((item) => <div className="metric-card" key={item.metric}><span>{item.metric.replace(/_/g, " ")}</span><strong>{item.current_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong><small>{item.status === "no_baseline" ? "No comparison baseline" : `${item.percent_change?.toFixed(1)}% vs prior period`}</small></div>)}</div>
          <p className="quiet">Sources: {Object.entries(report.source_timestamps).map(([key, value]) => `${key.replace(/_/g, " ")} · ${new Date(value).toLocaleString()}`).join(" · ")}</p>
        </section>
        <section className="panel"><h2>Findings and actions</h2>{report.findings.length === 0 ? <p>No high confidence issues were found in this report window.</p> : report.findings.map((finding, index) => {
          const recommendation = report.recommendations.find((item) => item.finding.code === finding.code && item.finding.summary === finding.summary);
          return <div className="finding-card" key={`${finding.code}-${index}`}><div className="finding-title"><div><h3>{finding.title}</h3><p>{finding.summary}</p></div><span className="confidence">{recommendation?.confidence ?? "evidence"}</span></div><MetricEvidence items={finding.evidence} />
            {recommendation && <div className="action-box"><strong>Suggested action</strong><p>{recommendation.suggested_action}</p><small>Measure: {recommendation.measurement}</small></div>}
            {finding.limitations.map((item) => <small className="quiet" key={item}>Limit: {item}</small>)}
          </div>;
        })}</section>
      </article>}
    </div>}
  </div>;
}
