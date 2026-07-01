import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { IngestPage } from "./IngestPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <TasksProvider>
        <IngestPage />
      </TasksProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["viagem"],
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
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    expect(fillBtn).toBeEnabled();
    await user.click(fillBtn);
    expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
    expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
  });

  it("loads options and shows the base name field", async () => {
    renderPage();
    expect(await screen.findByLabelText(/nome da base/i)).toBeInTheDocument();
  });

  it("calls ingest when Inserir is clicked with valid data", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome da base/i), "viagem");
    await user.click(await screen.findByRole("button", { name: /preencher tudo/i }));
    await user.click(screen.getByRole("button", { name: /inserir/i }));
    await waitFor(() =>
      expect(client.ingest).toHaveBeenCalledWith(expect.any(FormData)),
    );
  });
});
