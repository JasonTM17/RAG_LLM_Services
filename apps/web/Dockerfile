FROM node:24.12.0-bookworm-slim AS deps

WORKDIR /app
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY apps/web apps/web
RUN pnpm install --frozen-lockfile

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
ARG RAG_BACKEND_ORIGIN=http://api:8000
ENV RAG_BACKEND_ORIGIN=${RAG_BACKEND_ORIGIN}
RUN pnpm --filter @rag-llm-services/web build

FROM node:24.12.0-bookworm-slim AS runner

LABEL org.opencontainers.image.title="rag-llm-services-web"
LABEL org.opencontainers.image.description="Next.js Web UI for RAG LLM Services"
LABEL org.opencontainers.image.source="https://github.com/JasonTM17/RAG_LLM_Services"
LABEL org.opencontainers.image.licenses="MIT"

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=nextjs:nodejs /app/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
