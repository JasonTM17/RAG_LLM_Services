# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY packages/observability/pyproject.toml packages/observability/pyproject.toml
COPY packages/rag/pyproject.toml packages/rag/pyproject.toml
COPY packages/embeddings/pyproject.toml packages/embeddings/pyproject.toml
COPY packages/llm/pyproject.toml packages/llm/pyproject.toml
COPY packages/agents/pyproject.toml packages/agents/pyproject.toml
RUN --mount=type=cache,id=rag-uv-cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-workspace

COPY apps/api apps/api
COPY apps/worker apps/worker
COPY packages packages

RUN --mount=type=cache,id=rag-uv-cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY evals evals
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 9108

CMD ["sh", "-c", "celery -A rag_llm_services_worker.main:celery_app worker --loglevel=${WORKER_LOG_LEVEL:-INFO} --pool=${WORKER_POOL:-threads} --concurrency=${WORKER_CONCURRENCY:-4} --queues=${INGESTION_QUEUE_NAME:-ingestion}"]
