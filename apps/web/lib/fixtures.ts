import type {
  ApiClientPort,
  StreamHandlers,
} from "@/lib/api-client";
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

const OWNER_ID = "00000000-0000-0000-0000-000000000001";
const KB_ID = "10000000-0000-0000-0000-000000000001";
const DOC_ID = "20000000-0000-0000-0000-000000000001";
const CHUNK_ID = "30000000-0000-0000-0000-000000000001";
const CONVERSATION_ID = "40000000-0000-0000-0000-000000000001";
const MESSAGE_ID = "50000000-0000-0000-0000-000000000001";
const EVALUATION_ID = "60000000-0000-0000-0000-000000000001";

export const sampleKnowledgeBases: KnowledgeBase[] = [
  {
    id: KB_ID,
    owner_id: OWNER_ID,
    name: "Learning RAG",
    description: "Architecture notes and retrieval experiments",
    created_at: "2026-09-08T08:00:00Z",
    updated_at: "2026-09-08T08:30:00Z",
  },
];

export const sampleDocuments: DocumentSummary[] = [
  {
    id: DOC_ID,
    owner_id: OWNER_ID,
    knowledge_base_id: KB_ID,
    filename: "rag-overview.md",
    content_type: "text/markdown",
    status: "INDEXED",
    error_message: null,
    current_version_id: "21000000-0000-0000-0000-000000000001",
    chunk_count: 12,
    created_at: "2026-09-08T08:10:00Z",
    updated_at: "2026-09-08T08:25:00Z",
  },
];

export const sampleSource = {
  source_id: "[S1]",
  chunk_id: CHUNK_ID,
  document_id: DOC_ID,
  content:
    "Hybrid retrieval combines dense vector similarity and keyword search, then uses reciprocal rank fusion before reranking.",
  filename: "rag-overview.md",
  page: null,
  section: "Hybrid retrieval",
  token_count: 42,
  score: 0.92,
  retrieval_method: "hybrid",
  metadata: { section_header: "Hybrid retrieval" },
};

export const sampleChatResponse: ChatResponse = {
  conversation_id: CONVERSATION_ID,
  message_id: MESSAGE_ID,
  answer:
    "Hybrid retrieval mixes vector and keyword candidates, then ranks the merged set before context assembly [S1].",
  citations: [sampleSource],
  retrieved_sources: [sampleSource],
  usage: {
    input_tokens: 480,
    output_tokens: 36,
    cached_input_tokens: 0,
    total_tokens: 516,
    estimated_cost_usd: 0,
  },
  request_id: "web-test-request",
  provider: "fake",
  model: "deepseek-v4-flash",
  latency_ms: 42,
  retry_count: 0,
};

export class MockApiClient implements ApiClientPort {
  private knowledgeBases = [...sampleKnowledgeBases];
  private documents = [...sampleDocuments];
  private evaluationRun: EvaluationRun = {
    id: EVALUATION_ID,
    owner_id: OWNER_ID,
    status: "SUCCEEDED",
    idempotency_key: "web-smoke",
    trigger_source: "api",
    workflow_name: "manual-web-check",
    dataset_name: "baseline-learning-rag",
    report_path: "evals/reports/local/baseline-learning-rag.json",
    error_message: null,
    metadata_json: {},
    result: {
      status: "PASS",
      dataset_name: "baseline-learning-rag",
      example_count: 3,
      top_k: 5,
      metrics: {
        retrieval_hit_rate: 1,
        citation_correctness: 1,
        faithfulness: 0.667,
      },
    },
    created_at: "2026-09-08T09:00:00Z",
    updated_at: "2026-09-08T09:05:00Z",
  };

  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    return this.knowledgeBases;
  }

  async createKnowledgeBase(input: {
    name: string;
    description?: string | null;
  }): Promise<KnowledgeBase> {
    const kb = {
      id: crypto.randomUUID(),
      owner_id: OWNER_ID,
      name: input.name,
      description: input.description ?? null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    this.knowledgeBases = [kb, ...this.knowledgeBases];
    return kb;
  }

  async deleteKnowledgeBase(id: UUID): Promise<void> {
    this.knowledgeBases = this.knowledgeBases.filter((kb) => kb.id !== id);
  }

  async listDocuments(knowledgeBaseId?: UUID | null): Promise<DocumentSummary[]> {
    if (!knowledgeBaseId) {
      return this.documents;
    }
    return this.documents.filter((document) => document.knowledge_base_id === knowledgeBaseId);
  }

  async uploadDocument(input: {
    file: File;
    knowledgeBaseId: UUID;
  }): Promise<DocumentUploadResult> {
    const now = new Date().toISOString();
    const document: DocumentSummary = {
      id: crypto.randomUUID(),
      owner_id: OWNER_ID,
      knowledge_base_id: input.knowledgeBaseId,
      filename: input.file.name,
      content_type: input.file.type || "text/plain",
      status: "UPLOADED",
      error_message: null,
      current_version_id: crypto.randomUUID(),
      chunk_count: null,
      created_at: now,
      updated_at: now,
    };
    this.documents = [document, ...this.documents];
    return {
      document_id: document.id,
      version_id: document.current_version_id ?? crypto.randomUUID(),
      ingestion_job_id: crypto.randomUUID(),
      queue_task_id: "mock-task",
      queued: true,
      filename: document.filename,
      status: document.status,
      file_size_bytes: input.file.size,
      checksum_sha256: "mock-checksum",
      created_at: now,
    };
  }

  async reindexDocument(documentId: UUID): Promise<void> {
    this.documents = this.documents.map((document) =>
      document.id === documentId ? { ...document, status: "PARSING" } : document,
    );
  }

  async deleteDocument(documentId: UUID): Promise<void> {
    this.documents = this.documents.filter((document) => document.id !== documentId);
  }

  async getQueueStatus(): Promise<QueueStatus> {
    return { queue_name: "ingestion", depth: 2 };
  }

  async getLiveness(): Promise<HealthResponse> {
    return { status: "healthy" };
  }

  async getReadiness(): Promise<HealthResponse> {
    return { status: "healthy", checks: { postgres: "ok", redis: "ok", minio: "ok" } };
  }

  async createEvaluationRun(input: EvaluationCreateRequest): Promise<EvaluationRun> {
    void input;
    this.evaluationRun = { ...this.evaluationRun, status: "PENDING" };
    return this.evaluationRun;
  }

  async getEvaluationRun(runId: UUID): Promise<EvaluationRun> {
    void runId;
    return this.evaluationRun;
  }

  async chat(input: ChatRequest): Promise<ChatResponse> {
    void input;
    return sampleChatResponse;
  }

  async streamChat(_input: ChatRequest, handlers: StreamHandlers = {}): Promise<ChatStreamEvent> {
    const chunks = ["Hybrid retrieval ", "mixes vector and keyword candidates [S1]."];
    for (const delta of chunks) {
      const event = {
        event: "response.output_text.delta",
        delta,
        conversation_id: CONVERSATION_ID,
        message_id: null,
        usage: null,
        citations: [],
        retrieved_sources: [],
        error_code: null,
        error_message: null,
      };
      handlers.onEvent?.(event);
      handlers.onDelta?.(delta, event);
    }
    const completed = {
      event: "response.completed",
      delta: "",
      conversation_id: CONVERSATION_ID,
      message_id: MESSAGE_ID,
      usage: sampleChatResponse.usage,
      citations: sampleChatResponse.citations,
      retrieved_sources: sampleChatResponse.retrieved_sources,
      error_code: null,
      error_message: null,
    };
    handlers.onEvent?.(completed);
    handlers.onComplete?.(completed);
    return completed;
  }

  async createQuiz(input: QuizRequest): Promise<QuizResponse> {
    void input;
    return {
      ...studyBase(),
      questions: [
        {
          question: "Which ranking method merges vector and keyword candidates?",
          choices: ["RRF", "CRC32", "OAuth", "SMTP"],
          answer: "RRF",
          explanation: "The pipeline uses reciprocal rank fusion before reranking [S1].",
          citations: ["[S1]"],
        },
      ],
    };
  }

  async createFlashcards(input: FlashcardRequest): Promise<FlashcardSetResponse> {
    void input;
    return {
      ...studyBase(),
      cards: [
        {
          front: "Hybrid retrieval",
          back: "A retrieval mode that combines vector and keyword candidates before reranking [S1].",
          citations: ["[S1]"],
        },
      ],
    };
  }

  async createLearningPlan(input: LearningPlanRequest): Promise<LearningPlanResponse> {
    void input;
    return {
      ...studyBase(),
      days: [
        {
          day: 1,
          objective: "Trace the retrieval pipeline from search to cited answer.",
          activities: ["Review chunk candidates", "Compare vector and keyword hits"],
          check_yourself: "Explain where citations enter the response.",
          citations: ["[S1]"],
        },
      ],
    };
  }
}

function studyBase() {
  return {
    conversation_id: CONVERSATION_ID,
    message_id: MESSAGE_ID,
    topic: "Hybrid retrieval",
    difficulty: "intermediate",
    retrieved_sources: [sampleSource],
    request_id: "web-test-request",
    provider: "fake",
    model: "deepseek-v4-flash",
  };
}
