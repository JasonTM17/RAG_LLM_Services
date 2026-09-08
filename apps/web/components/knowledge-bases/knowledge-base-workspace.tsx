"use client";

import { Database, RefreshCcw, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError, type ApiClientPort } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { StatusBadge } from "@/components/ui/status-badge";
import type { KnowledgeBase, UUID } from "@/lib/types";

export function KnowledgeBaseWorkspace({ client = apiClient }: { client?: ApiClientPort }) {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<UUID | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await client.listKnowledgeBases();
      setItems(data);
      setSelectedId((current) => current ?? data[0]?.id ?? null);
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    client
      .listKnowledgeBases()
      .then((data) => {
        if (!active) {
          return;
        }
        setItems(data);
        setSelectedId((current) => current ?? data[0]?.id ?? null);
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

  const create = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!name.trim()) {
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const created = await client.createKnowledgeBase({
          name: name.trim(),
          description: description.trim() || null,
        });
        setName("");
        setDescription("");
        await refresh();
        setSelectedId(created.id);
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [client, description, name, refresh],
  );

  const remove = useCallback(
    async (id: UUID) => {
      setBusy(true);
      setError(null);
      try {
        await client.deleteKnowledgeBase(id);
        await refresh();
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [client, refresh],
  );

  return (
    <section className="page-stack" aria-labelledby="knowledge-title">
      <header className="page-header">
        <div>
          <h1 id="knowledge-title">Knowledge Bases</h1>
          <p>Manage source collections used by retrieval, chat, and study workflows.</p>
        </div>
        <button className="button" type="button" onClick={() => void refresh()}>
          <RefreshCcw size={16} aria-hidden="true" />
          Refresh
        </button>
      </header>

      <div className="kb-layout">
        <section className="panel">
          <div className="panel-header">
            <h2>Create</h2>
            <StatusBadge status={busy ? "RUNNING" : "READY"} />
          </div>
          <form className="panel-body field-grid" onSubmit={create}>
            {error ? <p className="error-note">{error}</p> : null}
            <label className="field">
              <span>Name</span>
              <input
                className="control"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Learning RAG"
              />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                className="textarea"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Architecture notes and retrieval experiments"
              />
            </label>
            <button className="button primary" type="submit" disabled={busy || !name.trim()}>
              <Database size={16} aria-hidden="true" />
              Create
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Collections</h2>
            <StatusBadge status={`${items.length} total`} />
          </div>
          <div className="kb-list">
            {items.length === 0 ? (
              <div className="empty-state">No knowledge bases.</div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={selected?.id === item.id ? "kb-item is-selected" : "kb-item"}
                  onClick={() => setSelectedId(item.id)}
                >
                  <strong>{item.name}</strong>
                  <span>{item.description || "No description"}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <aside className="panel">
          <div className="panel-header">
            <h2>Inspect</h2>
            {selected ? <StatusBadge status="SELECTED" /> : <StatusBadge status="EMPTY" />}
          </div>
          <div className="panel-body inspect-stack">
            {selected ? (
              <>
                <div>
                  <span className="label">Name</span>
                  <p>{selected.name}</p>
                </div>
                <div>
                  <span className="label">Description</span>
                  <p>{selected.description || "-"}</p>
                </div>
                <div className="kv-grid">
                  <div>
                    <span className="label">Created</span>
                    <p>{formatDateTime(selected.created_at)}</p>
                  </div>
                  <div>
                    <span className="label">Updated</span>
                    <p>{formatDateTime(selected.updated_at)}</p>
                  </div>
                </div>
                <button
                  className="button danger"
                  type="button"
                  disabled={busy}
                  onClick={() => void remove(selected.id)}
                >
                  <Trash2 size={16} aria-hidden="true" />
                  Delete
                </button>
              </>
            ) : (
              <div className="empty-state">Nothing selected.</div>
            )}
          </div>
        </aside>
      </div>
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
