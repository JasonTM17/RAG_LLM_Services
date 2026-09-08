export type UUID = string;

export type StatusTone = "neutral" | "good" | "warning" | "danger" | "info";

export interface KnowledgeBase {
  id: UUID;
  owner_id: UUID;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: UUID;
  version_number: number;
  file_size_bytes: number;
  checksum_sha256: string;
  mime_type: string;
  created_at: string;
}

export interface DocumentSummary {
  id: UUID;
  owner_id: UUID;
  knowledge_base_id: UUID;
  filename: string;
  content_type: string;
  status: string;
  error_message: string | null;
  current_version_id: UUID | null;
  chunk_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResult {
  document_id: UUID;
  version_id: UUID;
  ingestion_job_id: UUID;
  queue_task_id: string | null;
  queued: boolean;
  filename: string;
  status: string;
  file_size_bytes: number;
  checksum_sha256: string;
  created_at: string;
}

export interface QueueStatus {
  queue_name: string;
  depth: number;
}

export interface LLMUsage {
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface CitedChunk {
  source_id: string;
  chunk_id: UUID;
  document_id: UUID;
  content: string;
  filename: string;
  page: number | null;
  section: string | null;
  token_count: number;
  score: number;
  retrieval_method: "vector" | "keyword" | "hybrid" | string;
  metadata: Record<string, unknown>;
}

export interface ChatRequest {
  message: string;
  conversation_id?: UUID | null;
  knowledge_base_id?: UUID | null;
  max_output_tokens?: number | null;
  context_token_budget?: number | null;
}

export interface ChatResponse {
  conversation_id: UUID;
  message_id: UUID;
  answer: string;
  citations: CitedChunk[];
  retrieved_sources: CitedChunk[];
  usage: LLMUsage;
  request_id: string | null;
  provider: string;
  model: string;
  latency_ms: number;
  retry_count: number;
}

export interface ChatStreamEvent {
  event: string;
  delta: string;
  conversation_id: UUID | null;
  message_id: UUID | null;
  usage: LLMUsage | null;
  citations?: CitedChunk[];
  retrieved_sources?: CitedChunk[];
  error_code: string | null;
  error_message: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy" | string;
  checks?: Record<string, "ok" | "error" | string>;
}

export type StudyDifficulty = "beginner" | "intermediate" | "advanced" | string;

export interface StudyBaseRequest {
  topic: string;
  conversation_id?: UUID | null;
  knowledge_base_id?: UUID | null;
  difficulty: StudyDifficulty;
  max_output_tokens?: number | null;
  context_token_budget?: number | null;
}

export interface QuizRequest extends StudyBaseRequest {
  question_count: number;
}

export interface FlashcardRequest extends StudyBaseRequest {
  card_count: number;
}

export interface LearningPlanRequest extends StudyBaseRequest {
  days: number;
}

export interface QuizQuestion {
  question: string;
  choices: string[];
  answer: string;
  explanation: string;
  citations: string[];
}

export interface Flashcard {
  front: string;
  back: string;
  citations: string[];
}

export interface LearningPlanDay {
  day: number;
  objective: string;
  activities: string[];
  check_yourself: string;
  citations: string[];
}

export interface StudyResponseBase {
  conversation_id: UUID;
  message_id: UUID;
  topic: string;
  difficulty: StudyDifficulty;
  retrieved_sources: CitedChunk[];
  request_id: string | null;
  provider: string;
  model: string;
}

export interface QuizResponse extends StudyResponseBase {
  questions: QuizQuestion[];
}

export interface FlashcardSetResponse extends StudyResponseBase {
  cards: Flashcard[];
}

export interface LearningPlanResponse extends StudyResponseBase {
  days: LearningPlanDay[];
}

export interface EvaluationCreateRequest {
  trigger_source: "api" | "n8n";
  idempotency_key?: string | null;
  workflow_name?: string | null;
  dataset_name?: string | null;
  metadata?: Record<string, unknown>;
}

export interface EvaluationRun {
  id: UUID;
  owner_id: UUID;
  status: string;
  idempotency_key: string | null;
  trigger_source: string;
  workflow_name: string | null;
  dataset_name: string | null;
  report_path: string | null;
  error_message: string | null;
  metadata_json: Record<string, unknown>;
  result: EvaluationResult | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationResult {
  status?: string;
  dataset_name?: string;
  example_count?: number;
  top_k?: number;
  metrics?: Record<string, number>;
  thresholds?: Record<string, number>;
  generated_at?: string;
}
