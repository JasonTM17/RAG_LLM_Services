import { describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "@/lib/api-client";
import type { ChatStreamEvent } from "@/lib/types";

describe("HttpApiClient streamChat", () => {
  it("surfaces deltas, final citations, and terminal completion", async () => {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode(
            'event: response.output_text.delta\ndata: {"event":"response.output_text.delta","delta":"Hello ","conversation_id":"c","message_id":null,"usage":null,"error_code":null,"error_message":null}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(
            'event: response.completed\ndata: {"event":"response.completed","delta":"","conversation_id":"c","message_id":"m","usage":{"input_tokens":1,"output_tokens":1,"cached_input_tokens":0,"total_tokens":2,"estimated_cost_usd":0},"citations":[{"source_id":"[S1]","chunk_id":"30000000-0000-0000-0000-000000000001","document_id":"20000000-0000-0000-0000-000000000001","content":"Source text","filename":"rag.md","page":null,"section":"Intro","token_count":5,"score":0.9,"retrieval_method":"hybrid","metadata":{}}],"retrieved_sources":[],"error_code":null,"error_message":null}\n\n',
          ),
        );
        controller.close();
      },
    });

    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(stream, { status: 200 }))));

    const deltas: string[] = [];
    const events: ChatStreamEvent[] = [];
    const terminal = await new HttpApiClient().streamChat(
      { message: "hello" },
      {
        onDelta: (delta) => deltas.push(delta),
        onEvent: (event) => events.push(event),
      },
    );

    expect(deltas).toEqual(["Hello "]);
    expect(events).toHaveLength(2);
    expect(terminal.event).toBe("response.completed");
    expect(terminal.citations?.[0]?.source_id).toBe("[S1]");
  });

  it("returns incomplete when a stream ends without terminal event", async () => {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode(
            'event: response.output_text.delta\ndata: {"event":"response.output_text.delta","delta":"partial","conversation_id":"c","message_id":null,"usage":null,"error_code":null,"error_message":null}\n\n',
          ),
        );
        controller.close();
      },
    });

    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(stream, { status: 200 }))));

    const terminal = await new HttpApiClient().streamChat({ message: "hello" });

    expect(terminal.event).toBe("response.incomplete");
    expect(terminal.error_code).toBe("STREAM_INCOMPLETE");
  });

  it("attaches Authorization header when authToken is provided", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify([]), { status: 200 })),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new HttpApiClient("00000000-0000-0000-0000-000000000001", "test-jwt-token");
    await client.listKnowledgeBases();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/knowledge-bases",
      expect.objectContaining({
        headers: expect.objectContaining({
          authorization: "Bearer test-jwt-token",
          "x-user-id": "00000000-0000-0000-0000-000000000001",
        }),
      }),
    );
  });
});
