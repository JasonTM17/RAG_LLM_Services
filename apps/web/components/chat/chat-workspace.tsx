"use client";

import { Loader2, Send, SlidersHorizontal } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, ApiClientError, type ApiClientPort } from "@/lib/api-client";
import { AnswerWithCitations, SourceList } from "@/components/ui/citations";
import { StatusBadge } from "@/components/ui/status-badge";
import type { CitedChunk, ChatResponse, KnowledgeBase, UUID } from "@/lib/types";

type MessageStatus = "complete" | "streaming" | "failed" | "incomplete";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  citations: CitedChunk[];
  retrievedSources: CitedChunk[];
  provider?: string;
  model?: string;
  latencyMs?: number;
}

export function ChatWorkspace({ client = apiClient }: { client?: ApiClientPort }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<UUID | "">("");
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<UUID | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [useStream, setUseStream] = useState(true);
  const [showDebug, setShowDebug] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    client
      .listKnowledgeBases()
      .then((items) => {
        if (!active) {
          return;
        }
        setKnowledgeBases(items);
        setSelectedKnowledgeBaseId((current) => current || items[0]?.id || "");
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

  const latestSources = useMemo(() => {
    const assistant = [...messages].reverse().find((item) => item.role === "assistant");
    return assistant?.retrievedSources ?? [];
  }, [messages]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = message.trim();
      if (!trimmed || isSending) {
        return;
      }

      setError(null);
      setIsSending(true);
      setMessage("");

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        status: "complete",
        citations: [],
        retrievedSources: [],
      };
      const assistantId = crypto.randomUUID();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        status: useStream ? "streaming" : "complete",
        citations: [],
        retrievedSources: [],
      };

      setMessages((current) => [...current, userMessage, assistantMessage]);

      try {
        const payload = {
          message: trimmed,
          conversation_id: conversationId,
          knowledge_base_id: selectedKnowledgeBaseId || null,
        };

        if (!useStream) {
          const response = await client.chat(payload);
          setConversationId(response.conversation_id);
          setMessages((current) => applyCompletedResponse(current, assistantId, response));
          return;
        }

        await client.streamChat(payload, {
          onDelta: (delta) => {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId ? { ...item, content: item.content + delta } : item,
              ),
            );
          },
          onComplete: (streamEvent) => {
            setConversationId(streamEvent.conversation_id);
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      status: "complete",
                      citations: streamEvent.citations ?? [],
                      retrievedSources: streamEvent.retrieved_sources ?? [],
                    }
                  : item,
              ),
            );
          },
          onIncomplete: (streamEvent) => {
            setConversationId(streamEvent.conversation_id);
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId ? { ...item, status: "incomplete" } : item,
              ),
            );
          },
          onError: (streamEvent) => {
            setConversationId(streamEvent.conversation_id);
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId ? { ...item, status: "failed" } : item,
              ),
            );
            setError(streamEvent.error_message ?? "The streamed response failed.");
          },
        });
      } catch (err: unknown) {
        setError(errorMessage(err));
        setMessages((current) =>
          current.map((item) => (item.id === assistantId ? { ...item, status: "failed" } : item)),
        );
      } finally {
        setIsSending(false);
      }
    },
    [client, conversationId, isSending, message, selectedKnowledgeBaseId, useStream],
  );

  return (
    <section className="page-stack chat-page" aria-labelledby="chat-title">
      <header className="page-header">
        <div>
          <h1 id="chat-title">Chat</h1>
          <p>Grounded answers with inline citations and source inspection.</p>
        </div>
        <div className="toolbar">
          <label className="toggle">
            <input
              type="checkbox"
              checked={useStream}
              onChange={(event) => setUseStream(event.target.checked)}
            />
            Stream
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={showDebug}
              onChange={(event) => setShowDebug(event.target.checked)}
            />
            Debug
          </label>
        </div>
      </header>

      <div className="chat-layout">
        <section className="panel chat-transcript" aria-label="Conversation">
          <div className="panel-header">
            <h2>Conversation</h2>
            {isSending ? <StatusBadge status="RUNNING" /> : <StatusBadge status="READY" />}
          </div>
          <div className="message-list">
            {messages.length === 0 ? (
              <div className="empty-state">No conversation yet.</div>
            ) : (
              messages.map((item) => <MessageBubble key={item.id} message={item} />)
            )}
          </div>
          <form className="chat-composer" onSubmit={handleSubmit}>
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
                <span>Message</span>
                <textarea
                  className="textarea"
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Ask about indexed source material"
                />
              </label>
            </div>
            <div className="toolbar composer-actions">
              <button className="button primary" type="submit" disabled={isSending || !message.trim()}>
                {isSending ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
                Send
              </button>
            </div>
          </form>
        </section>

        <aside className="panel source-panel" aria-label="Sources">
          <div className="panel-header">
            <h2>Sources</h2>
            <StatusBadge status={`${latestSources.length} source${latestSources.length === 1 ? "" : "s"}`} />
          </div>
          <div className="panel-body">
            <SourceList sources={latestSources} />
          </div>
          {showDebug ? (
            <div className="debug-panel">
              <div className="debug-title">
                <SlidersHorizontal size={15} aria-hidden="true" />
                Retrieval Debug
              </div>
              <SourceList sources={latestSources} dense />
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={isAssistant ? "message assistant" : "message user"}>
      <div className="message-meta">
        <strong>{isAssistant ? "Assistant" : "You"}</strong>
        {isAssistant ? <StatusBadge status={message.status.toUpperCase()} /> : null}
      </div>
      {isAssistant ? (
        <AnswerWithCitations answer={message.content || "Waiting for response..."} citations={message.citations} />
      ) : (
        <p>{message.content}</p>
      )}
      {isAssistant && message.provider ? (
        <small className="muted">
          {message.provider} · {message.model} · {Math.round(message.latencyMs ?? 0)} ms
        </small>
      ) : null}
    </article>
  );
}

function applyCompletedResponse(
  messages: ChatMessage[],
  assistantId: string,
  response: ChatResponse,
): ChatMessage[] {
  return messages.map((item) =>
    item.id === assistantId
      ? {
          ...item,
          content: response.answer,
          status: "complete",
          citations: response.citations,
          retrievedSources: response.retrieved_sources,
          provider: response.provider,
          model: response.model,
          latencyMs: response.latency_ms,
        }
      : item,
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
