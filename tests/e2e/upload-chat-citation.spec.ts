import { expect, test } from "@playwright/test";

const ownerId = "00000000-0000-0000-0000-000000000001";
const kbId = "10000000-0000-0000-0000-000000000001";
const docId = "20000000-0000-0000-0000-000000000001";
const chunkId = "30000000-0000-0000-0000-000000000001";

const knowledgeBases = [
  {
    id: kbId,
    owner_id: ownerId,
    name: "Learning RAG",
    description: "Architecture notes and retrieval experiments",
    created_at: "2026-09-08T08:00:00Z",
    updated_at: "2026-09-08T08:30:00Z",
  },
];

const documents = [
  {
    id: docId,
    owner_id: ownerId,
    knowledge_base_id: kbId,
    filename: "rag-overview.md",
    content_type: "text/markdown",
    status: "INDEXED",
    error_message: null,
    current_version_id: "21000000-0000-0000-0000-000000000001",
    chunk_count: 12,
    created_at: "2026-09-08T08:10:00Z",
    updated_at: "2026-09-08T08:25:00Z",
  },
];

const source = {
  source_id: "[S1]",
  chunk_id: chunkId,
  document_id: docId,
  content: "Hybrid retrieval combines dense vector similarity and keyword search.",
  filename: "rag-overview.md",
  page: null,
  section: "Hybrid retrieval",
  token_count: 42,
  score: 0.92,
  retrieval_method: "hybrid",
  metadata: {},
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/knowledge-bases", async (route, request) => {
    if (request.method() === "GET") {
      await route.fulfill({ json: knowledgeBases });
      return;
    }
    await route.fallback();
  });

  await page.route("**/api/v1/documents**", async (route, request) => {
    if (request.method() === "GET") {
      await route.fulfill({ json: documents });
      return;
    }
    if (request.method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          document_id: "22000000-0000-0000-0000-000000000001",
          version_id: "23000000-0000-0000-0000-000000000001",
          ingestion_job_id: "24000000-0000-0000-0000-000000000001",
          queue_task_id: "mock-task",
          queued: true,
          filename: "uploaded.md",
          status: "UPLOADED",
          file_size_bytes: 14,
          checksum_sha256: "mock-checksum",
          created_at: "2026-09-08T10:00:00Z",
        },
      });
      return;
    }
    await route.fulfill({ status: 204, body: "" });
  });

  await page.route("**/api/v1/chat/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body:
        'event: response.output_text.delta\ndata: {"event":"response.output_text.delta","delta":"Hybrid retrieval mixes vector and keyword candidates ","conversation_id":"40000000-0000-0000-0000-000000000001","message_id":null,"usage":null,"error_code":null,"error_message":null}\n\n' +
        `event: response.completed\ndata: ${JSON.stringify({
          event: "response.completed",
          delta: "",
          conversation_id: "40000000-0000-0000-0000-000000000001",
          message_id: "50000000-0000-0000-0000-000000000001",
          usage: {
            input_tokens: 20,
            output_tokens: 8,
            cached_input_tokens: 0,
            total_tokens: 28,
            estimated_cost_usd: 0,
          },
          citations: [source],
          retrieved_sources: [source],
          error_code: null,
          error_message: null,
        })}\n\n`,
    });
  });
});

test("uploads a document and renders a cited streamed chat answer", async ({ page }) => {
  await page.goto("/documents");
  await expect(page.getByText("rag-overview.md")).toBeVisible();
  await expect(page.getByText("12")).toBeVisible();

  await page.getByLabel("File").setInputFiles({
    name: "uploaded.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("hello source"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("rag-overview.md")).toBeVisible();

  await page.getByRole("link", { name: /Chat/ }).click();
  await page.getByLabel("Message").fill("How does hybrid retrieval work?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText(/Hybrid retrieval mixes vector and keyword candidates/)).toBeVisible();
  await expect(page.getByText("[S1]").first()).toBeVisible();
  await expect(page.getByText("rag-overview.md").first()).toBeVisible();
});
