import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../src/App";
import { api } from "../src/api/client";
import type { ReportDetail, ReportSummary } from "../src/api/types";
import { ConnectionStatus } from "../src/components/ConnectionStatus";
import { MetricEvidence } from "../src/components/MetricEvidence";
import { SetupPage } from "../src/pages/SetupPage";
import { ReportPage } from "../src/pages/ReportPage";
import { ConnectionsPage } from "../src/pages/ConnectionsPage";

const reportSummary: ReportSummary = { id: "r1", created_at: "2026-10-18T10:00:00Z", date_range: "2026-09-01 to 2026-09-28", status: "ready", finding_count: 1, source_timestamps: {}, warning: null };
const detail: ReportDetail = {
  ...reportSummary, metrics: [], comparison: [], funnel: { cta_clicks: null, invite_submissions: null, status: "setup_needed", warning: "Map the invitation submission event before reporting conversion counts." },
  findings: [{ code: "search_low_ctr", title: "Low click-through rate", summary: "The query had 8 clicks.", source: "Google Search Console", evidence: [{ id: "gsc:q:clicks", metric: "clicks", value: 8, period: "2026-09-01", source: "Google Search Console", label: "tractor parts" }], limitations: [] }], recommendations: [],
};

beforeEach(() => {
  vi.spyOn(api, "me").mockResolvedValue({ email: "owner@example.com" });
  vi.spyOn(api, "googleStatus").mockResolvedValue({ connected: false, reconnect_required: false, search_console_site: null, ga4_property_id: null });
  vi.spyOn(api, "settings").mockResolvedValue({ site_url: null, search_console_site: null, ga4_property_id: null, cta_event: null, invite_submit_event: null });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.location.hash = ""; });

describe("private dashboard", () => {
  it("shows the sign-in gate for an unauthenticated owner", async () => {
    vi.mocked(api.me).mockRejectedValue(new Error("Request failed (401)"));
    render(<App />);
    expect(await screen.findByRole("button", { name: "Sign in with Google" })).toBeInTheDocument();
    expect(screen.getByText(/one configured owner account/i)).toBeInTheDocument();
  });

  it("shows Google connected and reconnect-required states", () => {
    const { rerender } = render(<ConnectionStatus status={{ connected: true, reconnect_required: false, search_console_site: null, ga4_property_id: null }} />);
    expect(screen.getByText("Google connected")).toBeInTheDocument();
    rerender(<ConnectionStatus status={{ connected: true, reconnect_required: true, search_console_site: null, ga4_property_id: null }} />);
    expect(screen.getByText("Reconnect Google")).toBeInTheDocument();
  });

  it("explains missing event mapping during setup", async () => {
    vi.spyOn(api, "properties").mockResolvedValue({ search_console: [], ga4: [], warnings: [] });
    render(<SetupPage status={{ connected: true, reconnect_required: false, search_console_site: null, ga4_property_id: null }} onRefresh={() => {}} onReport={() => {}} />);
    expect(await screen.findByText(/will show tracking setup as incomplete/i)).toBeInTheDocument();
  });

  it("warns when a saved report is stale and contains partial data", async () => {
    vi.spyOn(api, "reports").mockResolvedValue([{ ...reportSummary, created_at: "2026-09-01T10:00:00Z", status: "partial", warning: "Search Console incomplete" }]);
    vi.spyOn(api, "report").mockResolvedValue({ ...detail, created_at: "2026-09-01T10:00:00Z", status: "partial", warning: "Search Console incomplete" });
    render(<ReportPage onSelectReport={() => {}} />);
    expect(await screen.findByText(/over seven days old/i)).toBeInTheDocument();
    expect(screen.getByText(/some source data was incomplete/i)).toBeInTheDocument();
  });

  it("renders report evidence values and source dates", () => {
    render(<MetricEvidence items={detail.findings[0].evidence} />);
    expect(screen.getByText("clicks: 8")).toBeInTheDocument();
    expect(screen.getByText(/Google Search Console · 2026-09-01/)).toBeInTheDocument();
  });

  it("deletes a saved report and offers a Google disconnect control", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(api, "reports").mockResolvedValueOnce([reportSummary]).mockResolvedValueOnce([]);
    vi.spyOn(api, "report").mockResolvedValue(detail);
    const deleteReport = vi.spyOn(api, "deleteReport").mockResolvedValue(undefined);
    const disconnect = vi.spyOn(api, "disconnectGoogle").mockResolvedValue(undefined);
    const refresh = vi.fn();
    const { rerender } = render(<ReportPage onSelectReport={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete report" }));
    await waitFor(() => expect(deleteReport).toHaveBeenCalledWith("r1"));
    rerender(<ConnectionsPage status={{ connected: true, reconnect_required: false, search_console_site: "sc-domain:sparestracker.com", ga4_property_id: "123" }} settings={{ site_url: "https://sparestracker.com", search_console_site: "sc-domain:sparestracker.com", ga4_property_id: "123", cta_event: null, invite_submit_event: null }} onRefresh={refresh} />);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect and delete reports" }));
    await waitFor(() => expect(disconnect).toHaveBeenCalledOnce());
    expect(refresh).toHaveBeenCalledOnce();
  });
});
