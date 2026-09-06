# Contributing

## Workflow

1. Inspect repository state before editing.
2. Work from the active AgentKit plan under `plans/`.
3. Keep each change aligned to the current phase exit criterion.
4. Run the narrow verification command for the phase.
5. Stage explicit paths only.
6. Commit small logical units with Conventional Commits.

AgentKit contracts, runtime config, hooks, agents, plans, and documentation are source. Generated local skill mirrors under `.codex/skills/`, `.claude/skills/`, `.cursor/skills/`, and `.agents/skills/` are not source for this product repository; regenerate them locally when needed instead of staging them.

## Commit Style

Allowed prefixes:

- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `docs:`
- `chore:`
- `ci:`
- `perf:`
- `security:`

Do not force push. Do not combine unrelated feature, config, and documentation changes into one commit when they can be reviewed separately.

## Secret Policy

- Real secrets belong in `.env` or an external secret store.
- `.env.example` must contain placeholders only.
- Never commit API keys, passwords, auth headers, raw private documents, raw prompts, or provider error bodies that expose sensitive data.
- Before commit, run a credential-shaped scan that excludes `.env`.

## Evidence Policy

Report evidence using the narrowest truthful status:

- `LOCAL_PASS`
- `CI_PASS`
- `LIVE_PROVIDER_PASS`
- `DEPLOYED_PASS`
- `HOLD`
- `NOT_RUN`

Local checks do not prove CI, deployment, live provider behavior, backup restore, or production readiness.
