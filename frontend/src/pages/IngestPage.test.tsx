import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import type { GraphBuildJob } from "../api/types";
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
    llm_options: [
      { value: "gemini", label: "gemini", location: "remote" },
      { value: "qwen3:1.7b", label: "qwen3:1.7b", location: "local" },
    ],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["rouge_l"],
  });
  vi.mocked(client.ingest).mockResolvedValue({
    collections: ["viagem__recursive__gemini"],
    total_chunks: 12,
  });
  vi.mocked(client.listGraphBuilds).mockResolvedValue([]);
});

function job(status: GraphBuildJob["status"]): GraphBuildJob {
  return {
    id: 4, base: "viagem", extractor: "qwen3:1.7b", status, pause_requested: false,
    created_at: "2026-10-04T10:00:00Z", finished_at: null,
    indexes: [{
      chunking: "recursive", embedding: "e5", status: status === "running" ? "building" : "pending",
      extracted: 3, total: 12, stats: null, error: null,
    }],
  };
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText(/nome da base/i), "viagem");
  await user.upload(
    document.querySelector('input[type="file"]') as HTMLInputElement,
    new File(["texto"], "faq.md", { type: "text/markdown" }),
  );
  await user.click(await screen.findByRole("button", { name: /preencher tudo/i }));
}

function submittedForm(): FormData {
  return vi.mocked(client.ingest).mock.calls[0][0] as FormData;
}

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

  it("sends no LLM extrator unless 'Gerar Grafo de conhecimento' is checked", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    expect(screen.queryByRole("textbox", { name: /llm extrator/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));
    await waitFor(() => expect(client.ingest).toHaveBeenCalled());
    expect(submittedForm().get("graph_extractor")).toBeNull();
  });

  it("asks for the LLM extrator and sends it when the Grafo is wanted", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /gerar grafo de conhecimento/i }));
    expect(screen.getByRole("button", { name: /inserir documentos/i })).toBeDisabled();
    expect(screen.getByText(/ainda falta: o llm extrator/i)).toBeInTheDocument();

    await user.click(screen.getByRole("textbox", { name: /llm extrator/i }));
    await user.click(await screen.findByRole("option", { name: /qwen3:1.7b/ }));
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));
    await waitFor(() => expect(client.ingest).toHaveBeenCalled());
    expect(submittedForm().get("graph_extractor")).toBe("qwen3:1.7b");
  });

  it("follows the Grafo build: chunks extracted, pause and resume", async () => {
    vi.mocked(client.ingest).mockResolvedValue({
      collections: ["viagem__recursive__e5"], total_chunks: 12, graph_build: job("running"),
    });
    vi.mocked(client.listGraphBuilds).mockResolvedValue([job("running")]);
    vi.mocked(client.pauseGraphBuild).mockResolvedValue({ ...job("running"), pause_requested: true });
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /gerar grafo de conhecimento/i }));
    await user.click(screen.getByRole("textbox", { name: /llm extrator/i }));
    await user.click(await screen.findByRole("option", { name: /qwen3:1.7b/ }));
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));

    expect(await screen.findByText("Construindo Grafo: 3 / 12 trechos")).toBeInTheDocument();
    vi.mocked(client.listGraphBuilds).mockResolvedValue([job("paused")]);
    await user.click(screen.getByRole("button", { name: /pausar/i }));
    expect(client.pauseGraphBuild).toHaveBeenCalledWith(4);
    expect(await screen.findByText("Pausado")).toBeInTheDocument();

    vi.mocked(client.resumeGraphBuild).mockResolvedValue(job("pending"));
    vi.mocked(client.listGraphBuilds).mockResolvedValue([job("pending")]);
    await user.click(screen.getByRole("button", { name: /retomar/i }));
    expect(client.resumeGraphBuild).toHaveBeenCalledWith(4);
    expect(await screen.findByText("Na fila")).toBeInTheDocument();
  });

  it("shows Grafo builds already running when the page opens", async () => {
    vi.mocked(client.listGraphBuilds).mockResolvedValue([job("running")]);
    renderPage();
    expect(await screen.findByText("Construindo Grafo: 3 / 12 trechos")).toBeInTheDocument();
    expect(screen.getByText(/viagem/)).toBeInTheDocument();
  });

  it("prefills the base name from ?base=", async () => {
    renderPage("/ingest?base=santo%20Antonio");
    expect(await screen.findByDisplayValue("santo Antonio")).toBeInTheDocument();
  });

  it("shows the API's error message in PT-BR when ingest is refused (e.g. invalid base name)", async () => {
    vi.mocked(client.ingest).mockRejectedValue(
      new Error('Nome da base não pode conter "__": esse trecho separa base, corte e embedding no nome da coleção.'),
    );
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));

    expect(await screen.findByText(/os documentos não foram enviados/i)).toBeInTheDocument();
    expect(screen.getByText(/nome da base não pode conter/i)).toBeInTheDocument();
    // No false "started" message either, since the request actually failed.
    expect(screen.queryByText(/iniciada/i)).not.toBeInTheDocument();
  });

  it("disables Inserir while the ingestion is in flight, so a second click sends nothing", async () => {
    let finish!: (value: Awaited<ReturnType<typeof client.ingest>>) => void;
    vi.mocked(client.ingest).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    const button = screen.getByRole("button", { name: /inserir documentos/i });
    await user.click(button);

    await waitFor(() => expect(button).toBeDisabled());
    await user.click(button);
    expect(client.ingest).toHaveBeenCalledTimes(1);

    finish({ collections: ["viagem__recursive__e5"], total_chunks: 1, graph_build: null });
    expect(await screen.findByText(/ainda falta: os arquivos/i)).toBeInTheDocument();
    expect(client.ingest).toHaveBeenCalledTimes(1);
  });

  it("enables Inserir again when the ingestion is refused, to retry after fixing the form", async () => {
    vi.mocked(client.ingest).mockRejectedValue(new Error("Nome da base inválido."));
    renderPage();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: /inserir documentos/i }));

    expect(await screen.findByText(/os documentos não foram enviados/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /inserir documentos/i })).toBeEnabled();
  });
});
