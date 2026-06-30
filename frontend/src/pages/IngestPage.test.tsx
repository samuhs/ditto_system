import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { IngestPage } from "./IngestPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <IngestPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    chunkings: ["recursive", "fixed"],
    embeddings: ["gemini", "e5"],
    llms: ["gemini"],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["rouge_l"],
  });
  vi.mocked(client.ingest).mockResolvedValue({
    collections: ["viagem__recursive__gemini"],
    total_chunks: 12,
  });
});

describe("IngestPage", () => {
  it("loads options and shows the base name field", async () => {
    renderPage();
    expect(await screen.findByLabelText(/nome da base/i)).toBeInTheDocument();
  });

  it("submits the ingestion and shows the result", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome da base/i), "viagem");
    await user.click(screen.getByRole("button", { name: /inserir/i }));
    await waitFor(() =>
      expect(client.ingest).toHaveBeenCalledWith(expect.any(FormData)),
    );
    expect(await screen.findByText(/12/)).toBeInTheDocument();
  });
});
