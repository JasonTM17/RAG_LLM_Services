import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DocumentsWorkspace } from "@/components/documents/documents-workspace";
import { MockApiClient } from "@/lib/fixtures";

describe("DocumentsWorkspace", () => {
  it("shows document status, chunk count, and upload result", async () => {
    const user = userEvent.setup();
    render(<DocumentsWorkspace client={new MockApiClient()} />);

    expect(await screen.findByText("rag-overview.md")).toBeInTheDocument();
    expect(screen.getByText("INDEXED")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();

    const file = new File(["hello source"], "notes.md", { type: "text/markdown" });
    await user.upload(screen.getByLabelText("File"), file);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    const row = await screen.findByText("notes.md");
    expect(within(row.closest("tr") as HTMLElement).getByText("UPLOADED")).toBeInTheDocument();
  });
});
