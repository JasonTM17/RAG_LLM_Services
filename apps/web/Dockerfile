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

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /app/apps/web/public ./apps/web/public

EXPOSE 3000
CMD ["node", "apps/web/server.js"]
