"use client";

import { FileUp, RefreshCcw, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError, type ApiClientPort } from "@/lib/api-client";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { StatusBadge } from "@/components/ui/status-badge";
import type { DocumentSummary, KnowledgeBase, UUID } from "@/lib/types";

export function DocumentsWorkspace({ client = apiClient }: { client?: ApiClientPort }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<UUID | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [kbItems, docItems] = await Promise.all([
        client.listKnowledgeBases(),
        client.listDocuments(selectedKnowledgeBaseId || null),
      ]);
      setKnowledgeBases(kbItems);
      setDocuments(docItems);
      setSelectedKnowledgeBaseId((current) => current || kbItems[0]?.id || "");
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }, [client, selectedKnowledgeBaseId]);

  useEffect(() => {
    let active = true;
    Promise.all([
      client.listKnowledgeBases(),
      client.listDocuments(selectedKnowledgeBaseId || null),
    ])
      .then(([kbItems, docItems]) => {
        if (!active) {
          return;
        }
        setKnowledgeBases(kbItems);
        setDocuments(docItems);
        setSelectedKnowledgeBaseId((current) => current || kbItems[0]?.id || "");
      })
      .catch((err: unknown) => {
        if (active) {
          setError(errorMessage(err));
        }
      });
    return () => {
      active = false;
    };
  }, [client, selectedKnowledgeBaseId]);

  const upload = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!file || !selectedKnowledgeBaseId) {
        return;
      }
      setBusyId("upload");
      setError(null);
      try {
        await client.uploadDocument({ file, knowledgeBaseId: selectedKnowledgeBaseId });
        setFile(null);
        await refresh();
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusyId(null);
      }
    },
    [client, file, refresh, selectedKnowledgeBaseId],
  );

  const reindex = useCallback(
    async (documentId: UUID) => {
      setBusyId(documentId);
      setError(null);
      try {
        await client.reindexDocument(documentId);
        await refresh();
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusyId(null);
      }
    },
    [client, refresh],
  );

  const remove = useCallback(
    async (documentId: UUID) => {
      setBusyId(documentId);
      setError(null);
      try {
        await client.deleteDocument(documentId);
        await refresh();
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusyId(null);
      }
    },
    [client, refresh],
  );

  return (
    <section className="page-stack" aria-labelledby="documents-title">
      <header className="page-header">
        <div>
          <h1 id="documents-title">Documents</h1>
          <p>Upload source material and monitor ingestion status.</p>
        </div>
        <button className="button" type="button" onClick={() => void refresh()}>
          <RefreshCcw size={16} aria-hidden="true" />
          Refresh
        </button>
      </header>

      <section className="panel">
        <div className="panel-header">
          <h2>Upload</h2>
          {busyId === "upload" ? <StatusBadge status="UPLOADING" /> : <StatusBadge status="READY" />}
        </div>
        <form className="panel-body field-grid" onSubmit={upload}>
          {error ? <p className="error-note">{error}</p> : null}
          <div className="field-row">
            <label className="field">
              <span>Knowledge base</span>
              <select
                className="control"
                value={selectedKnowledgeBaseId}
                onChange={(event) => setSelectedKnowledgeBaseId(event.target.value)}
              >
                {knowledgeBases.length === 0 ? <option value="">No knowledge base</option> : null}
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>File</span>
              <input
                className="file-input"
                type="file"
                accept=".pdf,.txt,.md,.docx,text/plain,text/markdown,application/pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          <div className="toolbar">
            <button
              className="button primary"
              type="submit"
              disabled={!file || !selectedKnowledgeBaseId || busyId === "upload"}
            >
              <FileUp size={16} aria-hidden="true" />
              Upload
            </button>
            {file ? <span className="muted">{file.name} · {formatBytes(file.size)}</span> : null}
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Library</h2>
          <StatusBadge status={`${documents.length} document${documents.length === 1 ? "" : "s"}`} />
        </div>
        <div className="table-wrap">
          <table className="data-table documents-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Created</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {documents.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-state">No documents indexed.</div>
                  </td>
                </tr>
              ) : (
                documents.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <strong>{document.filename}</strong>
                      <small className="muted">{document.content_type}</small>
                      {document.error_message ? <small className="error-inline">{document.error_message}</small> : null}
                    </td>
                    <td>
                      <StatusBadge status={document.status} />
                    </td>
                    <td>{formatNumber(document.chunk_count)}</td>
                    <td>{formatDateTime(document.created_at)}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          type="button"
                          aria-label={`Reindex ${document.filename}`}
                          title="Reindex"
                          disabled={busyId === document.id}
                          onClick={() => void reindex(document.id)}
                        >
                          <RefreshCcw size={16} aria-hidden="true" />
                        </button>
                        <button
                          className="icon-button danger-icon"
                          type="button"
                          aria-label={`Delete ${document.filename}`}
                          title="Delete"
                          disabled={busyId === document.id}
                          onClick={() => void remove(document.id)}
                        >
                          <Trash2 size={16} aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
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
