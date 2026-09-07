# ADR-004: OpenAI Agents SDK and DeepSeek Provider

## Status

Accepted (2026-09-06): implementation begins with Phase 02; rationale recorded in docs/adr/ADR-007-toolchain.md context.

## Context

The platform needs agent workflows without depending on OpenAI Agent Builder UI. DeepSeek exposes OpenAI-compatible API surfaces and the project needs future provider flexibility.

## Decision

Use OpenAI Agents SDK in application code with a custom OpenAI-compatible DeepSeek client/provider behind the internal LLM gateway. Prefer Responses API mode at `https://api.deepseek.com` with model `deepseek-v4-flash`. Agent tools are server-scoped wrappers over application services; the model never supplies `owner_id` or talks to repositories directly.

## Consequences

- Business services call the gateway, not DeepSeek directly.
- Local/test runtime defaults to a fake LLM provider so automated tests and development do not make paid API calls.
- Production must set `LLM_PROVIDER=deepseek` and a real `DEEPSEEK_API_KEY`.
- Chat Completions fallback is disabled by default and must log a safe fallback reason when explicitly enabled.
- Provider-side continuation is not assumed; conversation state is stored locally.
- Live DeepSeek tests remain opt-in and use synthetic public prompts.
- Agent tool outputs are count- and size-bounded before entering model context.
- Retrieved document text is always marked as untrusted source data and cannot override system/developer instructions.

## Alternatives Considered

- OpenAI Agent Builder UI: rejected because runtime must be code-owned.
- Direct DeepSeek calls in services: rejected because it would prevent future provider swaps.
- Chat Completions first: reserved as explicit compatibility fallback.
