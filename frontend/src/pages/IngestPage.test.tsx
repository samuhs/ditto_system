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
  it("fills all fields when 'Preencher tudo' is clicked and shows 'Limpar tudo'; clears on second click", async () => {
    renderPage();
    const user = userEvent.setup();
    // Button appears disabled until options load, then enabled
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    expect(fillBtn).toBeEnabled();
    await user.click(fillBtn);
    // After fill, button label changes
    expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
    // Click again to clear
    await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
    expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
  });

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
