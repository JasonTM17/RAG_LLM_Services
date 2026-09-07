# Agent and LLM Gateway Architecture

Phase 06 added the provider-neutral LLM gateway and retrieval-grounded chat API. Phase 07 adds the OpenAI Agents SDK runtime definitions, bounded knowledge tools, Router/RAG/Study agent primitives, source-cited study endpoints, and shared citation validation. Agents call application services and typed tools; they do not query the database, object storage, or DeepSeek directly.

## Current Boundary

```text
POST /api/v1/chat
POST /api/v1/chat/stream
  -> ChatApplicationService
     -> ChatRepository
     -> RetrievalService
     -> CitationPromptBuilder
     -> LLMProvider
        -> FakeLLMProvider for local/test default
        -> DeepSeekProvider for configured runtime
     -> CitationValidator

POST /api/v1/study/quiz
POST /api/v1/study/flashcards
POST /api/v1/study/learning-plan
  -> AgentApplicationService
     -> StudyAgent
     -> KnowledgeBaseTools
        -> RetrievalService
        -> DocumentCatalogApplicationService
     -> LLMProvider
     -> CitationValidator
```

## Provider Rules

- Local and test default to `LLM_PROVIDER=fake` so normal development and CI do not make paid calls.
- Production must set `LLM_PROVIDER=deepseek` and a non-placeholder `DEEPSEEK_API_KEY`.
- `DEEPSEEK_BASE_URL` defaults to `https://api.deepseek.com` and rejects a `/v1` suffix.
- `DEEPSEEK_MODEL` defaults to `deepseek-v4-flash`.
- Responses API mode is the default; Chat Completions fallback is disabled unless explicitly enabled with a safe `fallback_reason`.
- Streaming is semantic Responses SSE: the API relays events such as `response.output_text.delta`, `response.completed`, `response.incomplete`, and `response.failed`; it does not use `data: [DONE]` as the application sentinel.

## Memory and Citations

- Conversation and message history are stored locally in `conversations` and `messages`.
- Provider-side continuation fields are not used.
- The prompt receives only the bounded `ContextBundle` or bounded tool output produced by retrieval.
- Retrieved context is wrapped as untrusted source data, never as instructions.
- Answers and study outputs are checked for `[S1]`-style source IDs; invented citations are rejected before commit.
- Usage and estimated cost are recorded in `llm_usage`; pricing defaults are configurable and may remain zero when current provider pricing has not been set by the operator.

## Agent Runtime

- `packages/agents` owns RouterAgent, RAGAgent, StudyAgent, prompt templates, context window trimming, citation validation, and OpenAI Agents SDK helper builders.
- SDK function tools capture `owner_id` server-side and expose only bounded inputs such as query, document ID, and result limits.
- Tool outputs truncate large chunks and context text before they enter model prompts.
- `openai-agents` is available for code-owned agent definitions; normal local tests still use `FakeLLMProvider`.
