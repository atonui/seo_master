import type { GoogleStatus } from "../api/types";

export function ConnectionStatus({ status }: { status: GoogleStatus | null }) {
  if (!status) return <span className="status-pill">Checking connection…</span>;
  if (!status.connected) return <span className="status-pill status-off">Google not connected</span>;
  if (status.reconnect_required) return <span className="status-pill status-warn">Reconnect Google</span>;
  return <span className="status-pill status-on">Google connected</span>;
}
