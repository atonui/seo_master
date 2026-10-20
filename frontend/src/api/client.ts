import type { ChatAnswer, GoogleStatus, Owner, PropertyList, ReportDetail, ReportSummary, ReportingSettings } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("owner-unauthorized"));
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<Owner>("/api/auth/me"),
  googleStatus: () => request<GoogleStatus>("/api/connections/google"),
  connectGoogle: () => request<{ authorization_url: string }>("/api/auth/google/start"),
  disconnectGoogle: () => request<void>("/api/connections/google", { method: "DELETE" }),
  properties: () => request<PropertyList>("/api/connections/google/properties"),
  settings: () => request<ReportingSettings>("/api/settings/reporting"),
  saveSettings: (payload: ReportingSettings) => request<ReportingSettings>("/api/settings/reporting", { method: "PUT", body: JSON.stringify(payload) }),
  reports: () => request<ReportSummary[]>("/api/reports"),
  report: (id: string) => request<ReportDetail>(`/api/reports/${encodeURIComponent(id)}`),
  runReport: (start_date?: string, end_date?: string) => request<ReportDetail>("/api/reports/run", { method: "POST", body: JSON.stringify(start_date && end_date ? { start_date, end_date } : {}) }),
  deleteReport: (id: string) => request<void>(`/api/reports/${encodeURIComponent(id)}`, { method: "DELETE" }),
  chat: (question: string, report_id?: string) => request<ChatAnswer>("/api/chat", { method: "POST", body: JSON.stringify({ question, report_id }) }),
};
