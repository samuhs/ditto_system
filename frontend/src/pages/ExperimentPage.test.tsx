import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { ExperimentPage, countCsvRecords } from "./ExperimentPage";

vi.mock("../api/client");

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
        { chunking: "fixed", embedding: "e5" },
        { chunking: "recursive", embedding: "gemini" },
      ],
    },
    chunkings: ["recursive", "fixed", "token"],
    embeddings: ["gemini", "e5"],
    llms: ["gemini"],
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

  it("lists real model names with a local/remote tag", async () => {
    vi.mocked(client.getOptions).mockResolvedValue({
      bases: ["teste-1"], chunkings: ["recursive"], embeddings: ["gemini"],
      llms: ["gemini-2.5-flash-lite", "qwen2.5:3b-instruct"],
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
