import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { useState } from "react";
import type { CitedChunk } from "@/lib/types";

const CITATION_RE = /(\[S\d+\])/g;

export function AnswerWithCitations({
  answer,
  citations,
}: {
  answer: string;
  citations: CitedChunk[];
}) {
  const sourceIds = new Set(citations.map((citation) => citation.source_id));
  return (
    <p className="answer-text">
      {answer.split(CITATION_RE).map((part, index) => {
        if (!sourceIds.has(part)) {
          return <span key={`${part}-${index}`}>{part}</span>;
        }
        return (
          <span key={`${part}-${index}`} className="citation-pill">
            {part}
          </span>
        );
      })}
    </p>
  );
}

export function SourceList({
  sources,
  dense = false,
}: {
  sources: CitedChunk[];
  dense?: boolean;
}) {
  if (sources.length === 0) {
    return <p className="muted">No sources returned.</p>;
  }

  return (
    <div className={dense ? "source-list dense" : "source-list"}>
      {sources.map((source) => (
        <SourceDisclosure key={`${source.source_id}-${source.chunk_id}`} source={source} />
      ))}
    </div>
  );
}

function SourceDisclosure({ source }: { source: CitedChunk }) {
  const [open, setOpen] = useState(false);

  return (
    <article className="source-card">
      <button
        type="button"
        className="source-head"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        <FileText size={16} aria-hidden="true" />
        <span>{source.source_id}</span>
        <strong title={source.filename}>{source.filename || "Untitled source"}</strong>
        <small>{formatSourceMeta(source)}</small>
      </button>
      {open ? (
        <div className="source-body">
          <p>{source.content}</p>
          <dl className="source-meta">
            <div>
              <dt>Score</dt>
              <dd>{source.score.toFixed(3)}</dd>
            </div>
            <div>
              <dt>Method</dt>
              <dd>{source.retrieval_method}</dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>{source.token_count}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </article>
  );
}

function formatSourceMeta(source: CitedChunk): string {
  const parts = [];
  if (source.section) {
    parts.push(source.section);
  }
  if (source.page) {
    parts.push(`p.${source.page}`);
  }
  return parts.join(" · ") || "chunk source";
}
