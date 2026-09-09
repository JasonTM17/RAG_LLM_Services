import type {
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  DocumentSummary,
  DocumentUploadResult,
  EvaluationCreateRequest,
  EvaluationRun,
  FlashcardRequest,
  FlashcardSetResponse,
  HealthResponse,
  KnowledgeBase,
  LearningPlanRequest,
  LearningPlanResponse,
  QueueStatus,
  QuizRequest,
  QuizResponse,
  UUID,
} from "@/lib/types";

const DEFAULT_OWNER_ID = "00000000-0000-0000-0000-000000000001";

type ApiBody = object | FormData | undefined;

export interface StreamHandlers {
  onEvent?: (event: ChatStreamEvent) => void;
  onDelta?: (delta: string, event: ChatStreamEvent) => void;
  onComplete?: (event: ChatStreamEvent) => void;
  onIncomplete?: (event: ChatStreamEvent) => void;
  onError?: (event: ChatStreamEvent) => void;
}

export interface ApiClientPort {
  listKnowledgeBases(): Promise<KnowledgeBase[]>;
  createKnowledgeBase(input: { name: string; description?: string | null }): Promise<KnowledgeBase>;
  deleteKnowledgeBase(id: UUID): Promise<void>;
  listDocuments(knowledgeBaseId?: UUID | null): Promise<DocumentSummary[]>;
  uploadDocument(input: { file: File; knowledgeBaseId: UUID }): Promise<DocumentUploadResult>;
  reindexDocument(documentId: UUID): Promise<void>;
  deleteDocument(documentId: UUID): Promise<void>;
  getQueueStatus(): Promise<QueueStatus>;
  getLiveness(): Promise<HealthResponse>;
  getReadiness(): Promise<HealthResponse>;
  createEvaluationRun(input: EvaluationCreateRequest): Promise<EvaluationRun>;
  getEvaluationRun(runId: UUID): Promise<EvaluationRun>;
  chat(input: ChatRequest): Promise<ChatResponse>;
  streamChat(input: ChatRequest, handlers?: StreamHandlers): Promise<ChatStreamEvent>;
  createQuiz(input: QuizRequest): Promise<QuizResponse>;
  createFlashcards(input: FlashcardRequest): Promise<FlashcardSetResponse>;
  createLearningPlan(input: LearningPlanRequest): Promise<LearningPlanResponse>;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

export class HttpApiClient implements ApiClientPort {
  private readonly ownerId: UUID;
  private readonly authToken?: string;

  constructor(ownerId: UUID = DEFAULT_OWNER_ID, authToken?: string) {
    this.ownerId = ownerId;
    this.authToken = authToken;
  }

  listKnowledgeBases(): Promise<KnowledgeBase[]> {
    return this.request<KnowledgeBase[]>("/api/v1/knowledge-bases");
  }

  createKnowledgeBase(input: {
    name: string;
    description?: string | null;
  }): Promise<KnowledgeBase> {
    return this.request<KnowledgeBase>("/api/v1/knowledge-bases", {
      method: "POST",
      body: input,
    });
  }

  deleteKnowledgeBase(id: UUID): Promise<void> {
    return this.request<void>(`/api/v1/knowledge-bases/${id}`, { method: "DELETE" });
  }

  listDocuments(knowledgeBaseId?: UUID | null): Promise<DocumentSummary[]> {
    const search = new URLSearchParams();
    if (knowledgeBaseId) {
      search.set("knowledge_base_id", knowledgeBaseId);
    }
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return this.request<DocumentSummary[]>(`/api/v1/documents${suffix}`);
  }

  uploadDocument(input: {
    file: File;
    knowledgeBaseId: UUID;
  }): Promise<DocumentUploadResult> {
    const body = new FormData();
    body.set("file", input.file);
    body.set("knowledge_base_id", input.knowledgeBaseId);
    return this.request<DocumentUploadResult>("/api/v1/documents", {
      method: "POST",
      body,
    });
  }

  async reindexDocument(documentId: UUID): Promise<void> {
    await this.request<unknown>(`/api/v1/documents/${documentId}/reindex`, { method: "POST" });
  }

  deleteDocument(documentId: UUID): Promise<void> {
    return this.request<void>(`/api/v1/documents/${documentId}`, { method: "DELETE" });
  }

  getQueueStatus(): Promise<QueueStatus> {
    return this.request<QueueStatus>("/api/v1/ingestion-jobs/queue");
  }

  getLiveness(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health/live");
  }

  getReadiness(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health/ready");
  }

  createEvaluationRun(input: EvaluationCreateRequest): Promise<EvaluationRun> {
    return this.request<EvaluationRun>("/api/v1/evaluations", {
      method: "POST",
      body: input,
    });
  }

  getEvaluationRun(runId: UUID): Promise<EvaluationRun> {
    return this.request<EvaluationRun>(`/api/v1/evaluations/${runId}`);
  }

  chat(input: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: input,
    });
  }

  async streamChat(input: ChatRequest, handlers: StreamHandlers = {}): Promise<ChatStreamEvent> {
    const response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: this.headers(true),
      body: JSON.stringify(input),
    });
    await assertOk(response);

    if (!response.body) {
      const event = incompleteEvent("Readable stream is not available in this browser.");
      handlers.onIncomplete?.(event);
      return event;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let terminalEvent: ChatStreamEvent | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const next = drainSseBuffer(buffer);
      buffer = next.remainder;
      for (const event of next.events) {
        terminalEvent = dispatchStreamEvent(event, handlers) ?? terminalEvent;
      }
    }

    buffer += decoder.decode();
    const final = drainSseBuffer(buffer + "\n\n");
    for (const event of final.events) {
      terminalEvent = dispatchStreamEvent(event, handlers) ?? terminalEvent;
    }

    if (!terminalEvent) {
      terminalEvent = incompleteEvent("The stream ended before a terminal event arrived.");
      handlers.onIncomplete?.(terminalEvent);
    }
    return terminalEvent;
  }

  createQuiz(input: QuizRequest): Promise<QuizResponse> {
    return this.request<QuizResponse>("/api/v1/study/quiz", {
      method: "POST",
      body: input,
    });
  }

  createFlashcards(input: FlashcardRequest): Promise<FlashcardSetResponse> {
    return this.request<FlashcardSetResponse>("/api/v1/study/flashcards", {
      method: "POST",
      body: input,
    });
  }

  createLearningPlan(input: LearningPlanRequest): Promise<LearningPlanResponse> {
    return this.request<LearningPlanResponse>("/api/v1/study/learning-plan", {
      method: "POST",
      body: input,
    });
  }

  private async request<T>(
    path: string,
    init: { method?: string; body?: ApiBody } = {},
  ): Promise<T> {
    let body: BodyInit | undefined;
    const requestBody = init.body;
    const isForm = requestBody instanceof FormData;
    if (isForm) {
      body = requestBody;
    } else if (requestBody) {
      body = JSON.stringify(requestBody);
    }
    const response = await fetch(path, {
      method: init.method ?? "GET",
      headers: this.headers(!isForm),
      body,
    });
    await assertOk(response);
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  private headers(json: boolean): HeadersInit {
    const headers: Record<string, string> = {
      "x-user-id": this.ownerId,
    };
    if (this.authToken) {
      headers["authorization"] = `Bearer ${this.authToken}`;
    }
    if (json) {
      headers["content-type"] = "application/json";
    }
    return headers;
  }
}

function dispatchStreamEvent(
  event: ChatStreamEvent,
  handlers: StreamHandlers,
): ChatStreamEvent | null {
  handlers.onEvent?.(event);
  if (event.delta) {
    handlers.onDelta?.(event.delta, event);
  }
  if (event.event === "response.completed") {
    handlers.onComplete?.(event);
    return event;
  }
  if (event.event === "response.incomplete") {
    handlers.onIncomplete?.(event);
    return event;
  }
  if (event.event === "response.failed" || event.error_code) {
    handlers.onError?.(event);
    return event;
  }
  return null;
}

function incompleteEvent(message: string): ChatStreamEvent {
  return {
    event: "response.incomplete",
    delta: "",
    conversation_id: null,
    message_id: null,
    usage: null,
    citations: [],
    retrieved_sources: [],
    error_code: "STREAM_INCOMPLETE",
    error_message: message,
  };
}

function drainSseBuffer(input: string): { events: ChatStreamEvent[]; remainder: string } {
  const events: ChatStreamEvent[] = [];
  const normalized = input.replaceAll("\r\n", "\n");
  const blocks = normalized.split("\n\n");
  const remainder = blocks.pop() ?? "";

  for (const block of blocks) {
    const event = parseSseBlock(block);
    if (event) {
      events.push(event);
    }
  }

  return { events, remainder };
}

function parseSseBlock(block: string): ChatStreamEvent | null {
  const dataLines: string[] = [];
  let eventName = "message";

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const payload = JSON.parse(dataLines.join("\n")) as Partial<ChatStreamEvent>;
  return {
    event: payload.event ?? eventName,
    delta: payload.delta ?? "",
    conversation_id: payload.conversation_id ?? null,
    message_id: payload.message_id ?? null,
    usage: payload.usage ?? null,
    citations: payload.citations ?? [],
    retrieved_sources: payload.retrieved_sources ?? [],
    error_code: payload.error_code ?? null,
    error_message: payload.error_message ?? null,
  };
}

async function assertOk(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiClientError(response.statusText || "Request failed", response.status);
  }

  const body = (await response.json()) as {
    error?: { code?: string; message?: string };
    detail?: string;
  };
  const message = body.error?.message ?? body.detail ?? "Request failed";
  throw new ApiClientError(message, response.status, body.error?.code ?? null);
}

export const apiClient = new HttpApiClient();
