import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ExperimentDetailPage } from "./ExperimentDetailPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/results/7"]}>
        <Routes>
          <Route path="/results/:id" element={<ExperimentDetailPage />} />
          <Route path="/results" element={<div>LISTA</div>} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getExperiment).mockResolvedValue({
    id: 7,
    name: "kind-ember-89",
    status: "done",
    results: [
      {
        chunking: "recursive",
        embedding: "gemini",
        rag: "naive",
        retriever: "similarity",
        llm: "gemini",
        question: "Pergunta A",
        answer: "Resposta A completa.",
        scores: { answer_relevancy: 0.2, faithfulness: 0.4 },
        latency_ms: 100,
        tokens: 10,
      },
      {
        chunking: "token",
        embedding: "gemini",
        rag: "agentic",
        retriever: "mmr",
        llm: "ollama",
        question: "Pergunta B",
        answer: "Resposta B completa.",
        scores: { answer_relevancy: 0.9, faithfulness: 0.8 },
        latency_ms: 200,
        tokens: 20,
      },
    ],
  });
});

async function openAnswers(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("tab", { name: /respostas por pergunta/i }));
}

describe("ExperimentDetailPage", () => {
  it("ranks combinations by their mean score and names the best one", async () => {
    renderPage();
    const winner = await screen.findByRole("region", { name: /melhor combinação/i });
    // token/agentic/mmr/ollama averages 0.85 vs 0.30 for the other combination
    expect(winner).toHaveTextContent("Por tokens");
    expect(winner).toHaveTextContent("Diversidade (MMR)");
    const rows = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    const idxToken = rows.findIndex((t) => t.includes("Por tokens"));
    const idxRecursive = rows.findIndex((t) => t.includes("Recursivo"));
    expect(idxToken).toBeGreaterThan(0);
    expect(idxToken).toBeLessThan(idxRecursive);
  });

  it("renders metric columns and a Média column, sorted by média desc by default", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    expect(await screen.findByRole("columnheader", { name: /answer_relevancy/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /faithfulness/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /média/i })).toBeInTheDocument();

    // default sort média desc → row B (avg 0.85) before row A (avg 0.30)
    const bodyText = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    const idxA = bodyText.findIndex((t) => t.includes("Pergunta A"));
    const idxB = bodyText.findIndex((t) => t.includes("Pergunta B"));
    expect(idxB).toBeGreaterThan(0);
    expect(idxB).toBeLessThan(idxA);
  });

  it("clicking a ranked combination shows only its answers", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /ver respostas da combinação 2/i }));
    expect(await screen.findByText("Pergunta A")).toBeInTheDocument();
    expect(screen.queryByText("Pergunta B")).not.toBeInTheDocument();
  });

  it("filters rows by retriever (mmr)", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await screen.findByText("Pergunta A");
    await user.click(screen.getAllByLabelText(/retrievers/i)[0]);
    await user.click(await screen.findByRole("option", { name: "Diversidade (MMR)" }));
    expect(screen.queryByText("Pergunta A")).not.toBeInTheDocument();
    expect(screen.getByText("Pergunta B")).toBeInTheDocument();
  });

  it("filters rows by llm (ollama)", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await screen.findByText("Pergunta A");
    await user.click(screen.getAllByLabelText(/llms/i)[0]);
    await user.click(await screen.findByRole("option", { name: "ollama" }));
    await waitFor(() => expect(screen.queryByText("Pergunta A")).not.toBeInTheDocument());
    expect(screen.getByText("Pergunta B")).toBeInTheDocument();
  });

  it("opens a drawer with full pergunta and resposta when a row is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await user.click(await screen.findByText(/Pergunta A/));
    expect(await screen.findByText("Detalhe do resultado")).toBeInTheDocument();
    // latency only renders inside the drawer
    expect(await screen.findByText(/100 ms/)).toBeInTheDocument();
  });

  it("shows a Pausar button for a running experiment and calls pauseExperiment", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "running",
      progress: { completed: 2, total: 8 },
      results: [],
    });
    vi.mocked(client.pauseExperiment).mockResolvedValue({ id: 7, status: "pausing" });
    renderPage();
    const user = userEvent.setup();
    const btn = await screen.findByRole("button", { name: /pausar/i });
    await user.click(btn);
    expect(client.pauseExperiment).toHaveBeenCalledWith(7);
  });

  it("goes back to the list", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /voltar aos experimentos/i }));
    expect(await screen.findByText("LISTA")).toBeInTheDocument();
  });

  it("shows a prompt button per technique and opens a read-only modal", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "done",
      prompts: {
        naive: { answer: "Answer using {context} and {question}." },
      },
      results: [
        {
          chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          llm: "gemini",
          question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1,
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /prompts usados/i }));
    const btn = await screen.findByRole("button", { name: /prompts: naive/i });
    await user.click(btn);
    expect(await screen.findByText(/Answer using/)).toBeInTheDocument();
  });

  it("shows the pausing state when pause is requested", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "running-exp",
      status: "running",
      pause_requested: true,
      progress: { completed: 1, total: 4 },
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/aguardando a combinação atual terminar/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pausando/i })).toBeDisabled();
  });

  it("shows a notice when the experiment has no prompt snapshot", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7, name: "old-exp", status: "done", results: [
        { chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          llm: "gemini",
          question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1 },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /prompts usados/i }));
    expect(await screen.findByText(/Prompts não registrados/i)).toBeInTheDocument();
  });

  it("shows start time and computed duration for a finished experiment", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "timed",
      status: "done",
      created_at: "2026-07-05T10:00:00.000Z",
      finished_at: "2026-07-05T10:02:10.000Z",
      progress: { completed: 1, total: 1 },
      results: [
        {
          chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          llm: "gemini", question: "Q", answer: "A", scores: { faithfulness: 0.8 }, latency_ms: 1, tokens: 1,
        },
      ],
    });
    renderPage();
    expect(await screen.findByText(/Duração 2m 10s/)).toBeInTheDocument();
  });

  it("shows a live duration while running", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "running",
      status: "running",
      created_at: new Date(Date.now() - 45000).toISOString(),
      progress: { completed: 0, total: 4 },
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/Duração/)).toBeInTheDocument();
  });

  it("offers a CSV export link for the experiment", async () => {
    vi.mocked(client.exportExperimentUrl).mockReturnValue("/api/experiments/7/export.csv");
    renderPage();
    const link = await screen.findByRole("link", { name: /Exportar CSV/ });
    expect(link).toHaveAttribute("href", "/api/experiments/7/export.csv");
    expect(link).toHaveAttribute("download");
    expect(client.exportExperimentUrl).toHaveBeenCalledWith(7);
  });
});
