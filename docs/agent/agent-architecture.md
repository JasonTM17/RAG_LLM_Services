# Agent and LLM Gateway Architecture

Phase 06 adds the provider-neutral LLM gateway and retrieval-grounded chat API that later agents consume. Agent orchestration itself arrives in Phase 07; agents must call application services and typed tools, not DeepSeek directly.

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
- The prompt receives only the bounded `ContextBundle` produced by retrieval.
- Answers are checked for `[S1]`-style source IDs, and the API returns both `citations` and `retrieved_sources`.
- Usage and estimated cost are recorded in `llm_usage`; pricing defaults are configurable and may remain zero when current provider pricing has not been set by the operator.
