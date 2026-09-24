import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { IngestPage } from "./IngestPage";

vi.mock("../api/client");

function renderPage(url = "/ingest") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <MantineProvider>
        <TasksProvider>
          <IngestPage />
        </TasksProvider>
      </MantineProvider>
    </MemoryRouter>,
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
    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["texto"], "faq.md", { type: "text/markdown" }),
    );
    await user.click(await screen.findByRole("button", { name: /preencher tudo/i }));
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));
    await waitFor(() =>
      expect(client.ingest).toHaveBeenCalledWith(expect.any(FormData)),
    );
  });

  it("keeps Inserir disabled and says what is missing until the form is complete", async () => {
    renderPage();
    await screen.findByRole("button", { name: /preencher tudo/i });
    expect(screen.getByRole("button", { name: /inserir documentos/i })).toBeDisabled();
    expect(screen.getByText(/ainda falta: o nome da base, os arquivos/i)).toBeInTheDocument();
  });

  it("explains each chunking technique next to its choice", async () => {
    renderPage();
    expect(await screen.findByText("Recursivo")).toBeInTheDocument();
    expect(screen.getByText(/corta por parágrafo/i)).toBeInTheDocument();
  });

  it("prefills the base name from ?base=", async () => {
    renderPage("/ingest?base=santo%20Antonio");
    expect(await screen.findByDisplayValue("santo Antonio")).toBeInTheDocument();
  });
});
