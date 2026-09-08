"use client";

import { BookOpenCheck, Layers3, ListChecks } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError, type ApiClientPort } from "@/lib/api-client";
import { SourceList } from "@/components/ui/citations";
import { StatusBadge } from "@/components/ui/status-badge";
import type {
  CitedChunk,
  FlashcardSetResponse,
  KnowledgeBase,
  LearningPlanResponse,
  QuizResponse,
  StudyDifficulty,
  UUID,
} from "@/lib/types";

type StudyMode = "quiz" | "flashcards" | "learning-plan";
type StudyResult =
  | { mode: "quiz"; data: QuizResponse }
  | { mode: "flashcards"; data: FlashcardSetResponse }
  | { mode: "learning-plan"; data: LearningPlanResponse };

export function StudyWorkspace({ client = apiClient }: { client?: ApiClientPort }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<UUID | "">("");
  const [mode, setMode] = useState<StudyMode>("quiz");
  const [topic, setTopic] = useState("Hybrid retrieval");
  const [difficulty, setDifficulty] = useState<StudyDifficulty>("intermediate");
  const [count, setCount] = useState(5);
  const [result, setResult] = useState<StudyResult | null>(null);
  const [busy, setBusy] = useState(false);
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

  const submit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!topic.trim()) {
        return;
      }
      setBusy(true);
      setError(null);
      const base = {
        topic: topic.trim(),
        difficulty,
        knowledge_base_id: selectedKnowledgeBaseId || null,
      };
      try {
        if (mode === "quiz") {
          setResult({ mode, data: await client.createQuiz({ ...base, question_count: count }) });
        }
        if (mode === "flashcards") {
          setResult({ mode, data: await client.createFlashcards({ ...base, card_count: count }) });
        }
        if (mode === "learning-plan") {
          setResult({ mode, data: await client.createLearningPlan({ ...base, days: count }) });
        }
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [client, count, difficulty, mode, selectedKnowledgeBaseId, topic],
  );

  const sources: CitedChunk[] = result?.data.retrieved_sources ?? [];

  return (
    <section className="page-stack" aria-labelledby="study-title">
      <header className="page-header">
        <div>
          <h1 id="study-title">Study</h1>
          <p>Generate cited quizzes, flashcards, and learning plans from indexed sources.</p>
        </div>
        <StatusBadge status={busy ? "RUNNING" : "READY"} />
      </header>

      <div className="study-layout">
        <section className="panel">
          <div className="panel-header">
            <h2>Generator</h2>
          </div>
          <form className="panel-body field-grid" onSubmit={submit}>
            {error ? <p className="error-note">{error}</p> : null}
            <div className="mode-tabs" role="tablist" aria-label="Study mode">
              <button
                type="button"
                className={mode === "quiz" ? "mode-tab is-active" : "mode-tab"}
                onClick={() => {
                  setMode("quiz");
                  setCount(5);
                }}
              >
                <ListChecks size={16} aria-hidden="true" />
                Quiz
              </button>
              <button
                type="button"
                className={mode === "flashcards" ? "mode-tab is-active" : "mode-tab"}
                onClick={() => {
                  setMode("flashcards");
                  setCount(10);
                }}
              >
                <Layers3 size={16} aria-hidden="true" />
                Cards
              </button>
              <button
                type="button"
                className={mode === "learning-plan" ? "mode-tab is-active" : "mode-tab"}
                onClick={() => {
                  setMode("learning-plan");
                  setCount(7);
                }}
              >
                <BookOpenCheck size={16} aria-hidden="true" />
                Plan
              </button>
            </div>
            <label className="field">
              <span>Topic</span>
              <input
                className="control"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
            </label>
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
                <span>Difficulty</span>
                <select
                  className="control"
                  value={difficulty}
                  onChange={(event) => setDifficulty(event.target.value)}
                >
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>{mode === "learning-plan" ? "Days" : "Items"}</span>
              <input
                className="control"
                type="number"
                min={1}
                max={mode === "flashcards" ? 50 : mode === "learning-plan" ? 30 : 20}
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
              />
            </label>
            <button className="button primary" type="submit" disabled={busy || !topic.trim()}>
              <BookOpenCheck size={16} aria-hidden="true" />
              Generate
            </button>
          </form>
        </section>

        <section className="panel study-output">
          <div className="panel-header">
            <h2>Output</h2>
            {result ? <StatusBadge status={result.mode.toUpperCase()} /> : <StatusBadge status="EMPTY" />}
          </div>
          <div className="panel-body">
            {result ? <StudyResultView result={result} /> : <div className="empty-state">No output yet.</div>}
          </div>
        </section>

        <aside className="panel">
          <div className="panel-header">
            <h2>Sources</h2>
            <StatusBadge status={`${sources.length} source${sources.length === 1 ? "" : "s"}`} />
          </div>
          <div className="panel-body">
            <SourceList sources={sources} dense />
          </div>
        </aside>
      </div>
    </section>
  );
}

function StudyResultView({ result }: { result: StudyResult }) {
  if (result.mode === "quiz") {
    return (
      <div className="study-result-list">
        {result.data.questions.map((question, index) => (
          <article className="study-card" key={`${question.question}-${index}`}>
            <strong>{question.question}</strong>
            <ol>
              {question.choices.map((choice) => (
                <li key={choice}>{choice}</li>
              ))}
            </ol>
            <p>{question.explanation}</p>
            <small className="muted">Answer: {question.answer}</small>
          </article>
        ))}
      </div>
    );
  }

  if (result.mode === "flashcards") {
    return (
      <div className="study-card-grid">
        {result.data.cards.map((card) => (
          <article className="study-card" key={card.front}>
            <strong>{card.front}</strong>
            <p>{card.back}</p>
          </article>
        ))}
      </div>
    );
  }

  return (
    <div className="study-result-list">
      {result.data.days.map((day) => (
        <article className="study-card" key={day.day}>
          <strong>Day {day.day}: {day.objective}</strong>
          <ul>
            {day.activities.map((activity) => (
              <li key={activity}>{activity}</li>
            ))}
          </ul>
          <p>{day.check_yourself}</p>
        </article>
      ))}
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
