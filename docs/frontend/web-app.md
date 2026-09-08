# Web Application

Phase 13 adds a Next.js App Router frontend under `apps/web`. It is an
operational workspace for the existing backend API, not a standalone LLM
client.

## Runtime Contract

- Node is pinned by `.node-version` to `24.12.0`.
- The workspace package manager is `pnpm@11.0.9`.
- Browser code calls same-origin routes only: `/api/v1/*` and `/health/*`.
- `RAG_BACKEND_ORIGIN` is read by Next.js server-side rewrites and defaults to
  `http://localhost:8000`.
- No `NEXT_PUBLIC_*` API base URL or provider key is required by the web app.

## Routes

- `/chat`: grounded chat with streaming, inline citations, source expansion,
  and optional retrieval debug display.
- `/documents`: upload, status, chunk count, reindex, and delete controls.
- `/knowledge-bases`: list, create, select, inspect, and delete collections.
- `/study`: source-cited quiz, flashcard, and learning-plan generation.
- `/system-status`: liveness, readiness checks, queue depth, and evaluation
  summary.

## Local Commands

```powershell
pnpm install --frozen-lockfile
pnpm web:dev
pnpm web:lint
pnpm web:typecheck
pnpm web:test
pnpm web:e2e
```

On Windows, Playwright uses the installed Edge Chromium channel by default.
Set `PLAYWRIGHT_CHANNEL=chrome` to use installed Chrome, or clear the variable
on systems that rely on Playwright-managed Chromium. Playwright starts the test
server on `127.0.0.1:43117` by default to avoid common local app ports; set
`WEB_E2E_PORT` when that port is unavailable.

Run the backend separately with:

```powershell
make api-run
```

For compose-based web development:

```powershell
docker compose --profile web up web
```

The compose web service binds `WEB_PORT` on the host and defaults to `3001` so
it can run beside Grafana's default `3000` host port.

## Verification

`scripts/verify-phase-13.ps1` runs frontend lint, type-check, unit/component
tests, build, mocked Playwright desktop/mobile e2e, backend API contract
regressions, compose config validation, secret scans, and `git diff --check`.
