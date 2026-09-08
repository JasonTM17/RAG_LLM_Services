import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { MockApiClient } from "@/lib/fixtures";

describe("ChatWorkspace", () => {
  it("streams an answer and renders citations with source details", async () => {
    const user = userEvent.setup();
    render(<ChatWorkspace client={new MockApiClient()} />);

    await screen.findByDisplayValue("Learning RAG");
    await user.type(screen.getByLabelText("Message"), "How does hybrid retrieval work?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/mixes vector and keyword candidates/)).toBeInTheDocument();
    expect(await screen.findAllByText("[S1]")).toHaveLength(2);
    expect(await screen.findByText("rag-overview.md")).toBeInTheDocument();
  });
});
