import type { StatusTone } from "@/lib/types";

const STATUS_TONE: Record<string, StatusTone> = {
  HEALTHY: "good",
  INDEXED: "good",
  SUCCEEDED: "good",
  PASS: "good",
  UPLOADED: "info",
  PENDING: "info",
  QUEUED: "info",
  RUNNING: "info",
  PARSING: "info",
  CHUNKING: "info",
  EMBEDDING: "info",
  DEGRADED: "warning",
  INCOMPLETE: "warning",
  FAILED: "danger",
  ERROR: "danger",
  UNHEALTHY: "danger",
};

export function statusTone(status: string | null | undefined): StatusTone {
  if (!status) {
    return "neutral";
  }
  return STATUS_TONE[status.toUpperCase()] ?? "neutral";
}

export function StatusBadge({
  status,
  tone,
}: {
  status: string | null | undefined;
  tone?: StatusTone;
}) {
  const resolved = tone ?? statusTone(status);
  return <span className={`status-badge status-${resolved}`}>{status ?? "Unknown"}</span>;
}
