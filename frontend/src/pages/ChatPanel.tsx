import { useState } from "react";
import { api } from "../api/client";
import type { ReportDetail } from "../api/types";

export function ChatPanel({ report }: { report: ReportDetail | null }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ text: string; refs: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true); setError("");
    try { const result = await api.chat(question.trim(), report?.id); setAnswer({ text: result.answer, refs: result.evidence_ids }); setQuestion(""); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="page-stack"><div className="page-title"><div><p className="eyebrow">ASK THE AGENT</p><h1>Ask about your data.</h1><p>The agent answers from a saved report and attaches its evidence references.</p></div></div>
    <section className="panel chat-panel"><div className="chat-context">Using report: {report?.date_range ?? "latest saved report"}</div>
      {!answer && <p className="quiet">Try: “Which finding should I address first?” or “What does the Search Console data show?”</p>}
      {answer && <div className="chat-answer"><p>{answer.text}</p><small>Evidence: {answer.refs.join(", ")}</small></div>}
      {error && <p role="alert" className="error-box">{error}</p>}
      <form onSubmit={ask} className="chat-form"><label htmlFor="question">Your question</label><textarea id="question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about your latest report" rows={3} /><button className="button-primary" disabled={busy || !question.trim()}>{busy ? "Thinking…" : "Ask"}</button></form>
    </section>
  </div>;
}
