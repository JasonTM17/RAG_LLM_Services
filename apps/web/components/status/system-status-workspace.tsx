"use client";

import { Activity, BarChart3, Play, RefreshCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, ApiClientError, type ApiClientPort } from "@/lib/api-client";
import { formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import { StatusBadge } from "@/components/ui/status-badge";
import type { EvaluationRun, HealthResponse, QueueStatus } from "@/lib/types";

export function SystemStatusWorkspace({ client = apiClient }: { client?: ApiClientPort }) {
  const [live, setLive] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<HealthResponse | null>(null);
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [liveData, readyData, queueData] = await Promise.all([
        client.getLiveness(),
        client.getReadiness(),
        client.getQueueStatus(),
      ]);
      setLive(liveData);
      setReady(readyData);
      setQueue(queueData);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    Promise.all([client.getLiveness(), client.getReadiness(), client.getQueueStatus()])
      .then(([liveData, readyData, queueData]) => {
        if (!active) {
          return;
        }
        setLive(liveData);
        setReady(readyData);
        setQueue(queueData);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(errorMessage(err));
        }
      });
    return () => {
      active = false;
    };
  }, [client]);

  const runEvaluation = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await client.createEvaluationRun({
        trigger_source: "api",
        idempotency_key: `web-${new Date().toISOString().slice(0, 10)}`,
        workflow_name: "manual-web-check",
      });
      setEvaluation(created);
      const latest = await client.getEvaluationRun(created.id);
      setEvaluation(latest);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }, [client]);

  const metrics = useMemo(() => evaluation?.result?.metrics ?? {}, [evaluation]);

  return (
    <section className="page-stack" aria-labelledby="status-title">
      <header className="page-header">
        <div>
          <h1 id="status-title">System Status</h1>
          <p>API readiness, queue depth, and latest RAG evaluation summary.</p>
        </div>
        <div className="toolbar">
          <button className="button" type="button" onClick={() => void refresh()} disabled={busy}>
            <RefreshCcw size={16} aria-hidden="true" />
            Refresh
          </button>
          <button className="button primary" type="button" onClick={() => void runEvaluation()} disabled={busy}>
            <Play size={16} aria-hidden="true" />
            Evaluate
          </button>
        </div>
      </header>

      {error ? <p className="error-note">{error}</p> : null}

      <div className="status-grid">
        <StatusPanel title="Liveness" icon={<Activity size={18} aria-hidden="true" />} status={live?.status} />
        <StatusPanel title="Readiness" icon={<Activity size={18} aria-hidden="true" />} status={ready?.status} />
        <StatusPanel
          title="Queue"
          icon={<BarChart3 size={18} aria-hidden="true" />}
          status={queue ? `${queue.depth} pending` : "Unknown"}
        />
        <StatusPanel
          title="Evaluation"
          icon={<BarChart3 size={18} aria-hidden="true" />}
          status={evaluation?.status ?? "Not run"}
        />
      </div>

      <div className="status-layout">
        <section className="panel">
          <div className="panel-header">
            <h2>Readiness Checks</h2>
            <StatusBadge status={ready?.status ?? "UNKNOWN"} />
          </div>
          <div className="panel-body readiness-list">
            {ready?.checks ? (
              Object.entries(ready.checks).map(([name, status]) => (
                <div className="readiness-row" key={name}>
                  <span>{name}</span>
                  <StatusBadge status={status} />
                </div>
              ))
            ) : (
              <div className="empty-state">No readiness response.</div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Evaluation Summary</h2>
            <StatusBadge status={evaluation?.result?.status ?? evaluation?.status ?? "EMPTY"} />
          </div>
          <div className="panel-body evaluation-summary">
            {evaluation ? (
              <>
                <div className="kv-grid">
                  <div>
                    <span className="label">Dataset</span>
                    <p>{evaluation.dataset_name ?? evaluation.result?.dataset_name ?? "-"}</p>
                  </div>
                  <div>
                    <span className="label">Updated</span>
                    <p>{formatDateTime(evaluation.updated_at)}</p>
                  </div>
                </div>
                <div className="metric-grid">
                  <Metric label="Hit rate" value={formatPercent(metrics.retrieval_hit_rate)} />
                  <Metric label="Citation" value={formatPercent(metrics.citation_correctness)} />
                  <Metric label="Faithful" value={formatPercent(metrics.faithfulness)} />
                  <Metric label="Examples" value={formatNumber(evaluation.result?.example_count)} />
                </div>
                {evaluation.error_message ? <p className="error-note">{evaluation.error_message}</p> : null}
              </>
            ) : (
              <div className="empty-state">No evaluation run loaded.</div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function StatusPanel({
  title,
  icon,
  status,
}: {
  title: string;
  icon: React.ReactNode;
  status: string | null | undefined;
}) {
  return (
    <article className="status-panel panel">
      <div>
        {icon}
        <span>{title}</span>
      </div>
      <StatusBadge status={status ?? "Unknown"} />
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return `${error.code ?? error.status}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}
