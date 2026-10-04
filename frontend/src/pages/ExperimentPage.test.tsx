import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { ExperimentPage, countCsvRecords } from "./ExperimentPage";

vi.mock("../api/client");

const EXTRACTOR = "mlx-community/Qwen2.5-3B-Instruct-4bit";

function renderPage() {
  return render(
    <MemoryRouter>
      <MantineProvider>
        <TasksProvider>
          <ExperimentPage />
        </TasksProvider>
      </MantineProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["teste-1"],
    base_indexes: {
      "teste-1": [
        { chunking: "fixed", embedding: "e5", graph_extractors: [EXTRACTOR] },
        { chunking: "recursive", embedding: "gemini", graph_extractors: [EXTRACTOR] },
      ],
    },
    chunkings: ["recursive", "fixed", "token"],
    embeddings: ["gemini", "e5"],
    llm_options: [{ value: "gemini", label: "gemini", location: "remote" }],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["answer_relevancy"],
  });
  vi.mocked(client.createExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "pending" });
  vi.mocked(client.getExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "done", results: [] });
});

const CSV = "pergunta,resposta_referencia\nOnde fica?,No centro.\nQuando abre?,\"Às 9h,\nsegunda a sexta\"\n";

async function fillValidForm(user: ReturnType<typeof userEvent.setup>, { pickBase = true } = {}) {
  await screen.findByRole("button", { name: /preencher tudo/i });
  if (pickBase) {
    await user.click(screen.getByRole("textbox", { name: /^base$/i }));
    await user.click(await screen.findByRole("option", { name: "teste-1" }));
  }
  await user.click(screen.getByRole("button", { name: /preencher tudo/i }));
  await user.upload(
    document.querySelector('input[type="file"]') as HTMLInputElement,
    new File([CSV], "perguntas.csv", { type: "text/csv" }),
  );
}

function submittedConfig() {
  const form = vi.mocked(client.createExperiment).mock.calls[0][0] as FormData;
  return JSON.parse(form.get("config") as string);
}

describe("ExperimentPage", () => {
  it("shows memory warnings returned on creation", async () => {
    vi.mocked(client.createExperiment).mockResolvedValue({
      id: 8, name: "x", status: "pending", warnings: ["A concorrência pedida (8) passa do limite"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    expect(await screen.findByText(/concorrência pedida \(8\)/)).toBeInTheDocument();
  });

  it("keeps Gerar disabled and lists what is missing until the form is complete", async () => {
    renderPage();
    await screen.findByRole("button", { name: /preencher tudo/i });
    expect(screen.getByRole("button", { name: /gerar experimento/i })).toBeDisabled();
    expect(screen.getByText(/ainda falta: a base/i)).toBeInTheDocument();
  });

  it("calls createExperiment when Gerar is clicked with a complete form", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() =>
      expect(client.createExperiment).toHaveBeenCalledWith(expect.any(FormData)),
    );
    expect(await screen.findByRole("link", { name: /acompanhar/i })).toHaveAttribute("href", "/results/7");
  });

  it("fills all 5 fields when 'Preencher tudo' is clicked and clears on 'Limpar tudo'", async () => {
    renderPage();
    const user = userEvent.setup();
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    expect(fillBtn).toBeEnabled();
    await user.click(fillBtn);
    expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
    expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
  });

  it("includes llms and concurrency 1 by default in the submitted config", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig().llms).toEqual(["gemini"]);
    expect(submittedConfig().concurrency).toBe(1);
  });

  it("shows the run size before committing: combinations × questions", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    // 2 indexes × 1 rag × 1 retriever × 1 llm = 2 combinations; 2 questions → 4 answers
    expect(await screen.findByText(/2 perguntas encontradas/i)).toBeInTheDocument();
    expect(screen.getByText("respostas a gerar e avaliar").previousElementSibling).toHaveTextContent("4");
  });

  it("offers the Grafo technique and runs it once per index, not per retriever", async () => {
    const options = await client.getOptions();
    vi.mocked(client.getOptions).mockResolvedValue({
      ...options, rags: ["naive", "graph"], retrievers: ["similarity", "mmr"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    expect(screen.getByText("Grafo (GraphRAG)")).toBeInTheDocument();
    expect(await screen.findByText(/2 perguntas encontradas/i)).toBeInTheDocument();
    // naive: 2 indexes × 2 retrievers = 4; graph: 2 indexes = 2; 6 combinations × 2 questions
    expect(screen.getByText("respostas a gerar e avaliar").previousElementSibling).toHaveTextContent("12");
  });

  it("offers the Grafo + busca technique and runs it per index and retriever", async () => {
    const options = await client.getOptions();
    vi.mocked(client.getOptions).mockResolvedValue({
      ...options, rags: ["graph_mix"], retrievers: ["similarity", "mmr"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    expect(screen.getByText("Grafo + busca")).toBeInTheDocument();
    expect(await screen.findByText(/2 perguntas encontradas/i)).toBeInTheDocument();
    // graph_mix: 2 indexes × 2 retrievers = 4 combinations × 2 questions
    expect(screen.getByText("respostas a gerar e avaliar").previousElementSibling).toHaveTextContent("8");
  });

  it("offers graph and graph_mix only while every chosen index has a Grafo", async () => {
    const options = await client.getOptions();
    vi.mocked(client.getOptions).mockResolvedValue({
      ...options,
      base_indexes: {
        "teste-1": [
          { chunking: "fixed", embedding: "e5", graph_extractors: [EXTRACTOR] },
          { chunking: "recursive", embedding: "gemini", graph_extractors: [] },
        ],
      },
      rags: ["naive", "graph", "graph_mix"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    expect(screen.queryByText("Grafo (GraphRAG)")).not.toBeInTheDocument();
    expect(screen.getByText(/aparecem quando todos os índices marcados/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /gere o grafo na ingestão/i })).toHaveAttribute(
      "href", "/ingest?base=teste-1",
    );

    await user.click(screen.getByRole("checkbox", { name: /recursive · gemini/ }));
    expect(screen.getByText("Grafo (GraphRAG)")).toBeInTheDocument();
    expect(screen.queryByText(/aparecem quando todos os índices marcados/i)).not.toBeInTheDocument();
  });

  it("submits the LLM extrator common to the chosen indexes' Grafos", async () => {
    const options = await client.getOptions();
    vi.mocked(client.getOptions).mockResolvedValue({
      ...options,
      base_indexes: {
        "teste-1": [
          { chunking: "fixed", embedding: "e5", graph_extractors: ["qwen3:1.7b", EXTRACTOR] },
          { chunking: "recursive", embedding: "gemini", graph_extractors: ["qwen3:1.7b", EXTRACTOR] },
        ],
      },
      rags: ["naive", "graph"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    const select = screen.getByRole("textbox", { name: /llm extrator do grafo/i });
    expect(select).toHaveValue("qwen3:1.7b");
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: EXTRACTOR }));
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig()).toMatchObject({ rags: ["naive", "graph"], graph_extractor: EXTRACTOR });
  });

  it("sends no LLM extrator without a Grafo technique", async () => {
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    expect(screen.queryByRole("textbox", { name: /llm extrator do grafo/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    expect(submittedConfig().graph_extractor).toBeUndefined();
  });

  it("lists real model names with a local/remote tag", async () => {
    vi.mocked(client.getOptions).mockResolvedValue({
      bases: ["teste-1"], chunkings: ["recursive"], embeddings: ["gemini"],
      llm_options: [
        { value: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite", location: "remote" },
        { value: "qwen2.5:3b-instruct", label: "qwen2.5:3b-instruct", location: "local" },
      ],
      rags: ["naive"], retrievers: ["similarity"], metrics: ["answer_relevancy"],
    });
    renderPage();
    expect(await screen.findByText("qwen2.5:3b-instruct")).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
    expect(screen.getByText("remoto")).toBeInTheDocument();
  });

  it("offers only the indexes of the chosen base, all preselected, and submits the pairs", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(screen.getByRole("textbox", { name: /^base$/i }));
    await user.click(await screen.findByRole("option", { name: "teste-1" }));
    expect(screen.getByRole("checkbox", { name: /fixed · e5/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /recursive · gemini/ })).toBeChecked();
    expect(screen.getByRole("link", { name: /indexar mais variações/i })).toHaveAttribute(
      "href",
      "/ingest?base=teste-1",
    );
    await fillValidForm(user, { pickBase: false });
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    const config = submittedConfig();
    expect(config.indexes).toEqual([
      { chunking: "fixed", embedding: "e5" },
      { chunking: "recursive", embedding: "gemini" },
    ]);
    expect(config.chunkings).toEqual(["fixed", "recursive"]);
    expect(config.embeddings).toEqual(["e5", "gemini"]);
  });
});

describe("countCsvRecords", () => {
  it("counts data rows, excluding the header and honouring quoted line breaks", () => {
    expect(countCsvRecords(CSV)).toBe(2);
    expect(countCsvRecords("pergunta,resposta_referencia\r\na,b\r\n\r\n")).toBe(1);
    expect(countCsvRecords("")).toBe(0);
  });
});
