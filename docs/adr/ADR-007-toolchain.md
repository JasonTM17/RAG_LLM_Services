# ADR-007: Toolchain Selection

## Status

Accepted (2026-09-06)

## Context

Phase 02 (Backend Foundation) requires a locked Python/package-manager and
frontend toolchain. The selection must work on Windows development hosts and
later in Docker Compose, support a growing multi-package layout (apps/api,
apps/worker, packages/*), and pin reproducibly.

## Decision

- Python `3.13` managed by `uv`, with a virtual uv workspace at the repository
  root (`[tool.uv.workspace]`) whose members are `apps/api`,
  `packages/shared`, and `packages/observability` (later phases add
  `apps/worker`, `packages/llm`, `packages/rag`, and friends as members).
- Backend web framework: FastAPI with Pydantic v2 and pydantic-settings.
- Database access: SQLAlchemy 2.x async with `psycopg[binary]` 3.x
  (`postgresql+psycopg://` driver); migrations with Alembic using the async
  template.
- Frontend (Phase 13): Node `24.12.0` with `pnpm` and Next.js.

## Consequences

- One `uv.lock` and one virtual environment cover all Python members; new
  packages join the workspace without re-architecture.
- `uv` provisions Python 3.13 itself, so host Python versions do not matter.
- `psycopg[binary]` ships prebuilt Windows and Linux wheels for CPython 3.13,
  avoiding local compiler requirements.
- `uv` is a new dependency for contributors; `README.md` records the install
  path and `.python-version` pins the interpreter.

## Alternatives Considered

- `pip` + `venv` per package: rejected; no lockfile story across members and
  manual environment wiring for every new package.
- Poetry: rejected; workspace handling for mixed apps/packages is weaker and
  adds a second lock/tool ecosystem to the team contract.
- System Python (3.14.x on current hosts): rejected; the plan pins 3.13 and
  provider wheels are validated against it.
- `npm`/`yarn` for the frontend: rejected; the repo contract already standardizes
  on `pnpm` with Node 24.
