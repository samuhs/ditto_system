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

describe("ExperimentDetailPage", () => {
  it("renders metric columns and a Média column, sorted by média desc by default", async () => {
    renderPage();
    // header cells for metrics + média
    expect(await screen.findByRole("columnheader", { name: /answer_relevancy/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /faithfulness/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /média/i })).toBeInTheDocument();

    // default sort média desc → row B (avg 0.85) before row A (avg 0.30)
    const rows = screen.getAllByRole("row");
    // rows[0] is the header; find the data rows containing questions
    const bodyText = rows.map((r) => r.textContent ?? "");
    const idxA = bodyText.findIndex((t) => t.includes("Pergunta A"));
    const idxB = bodyText.findIndex((t) => t.includes("Pergunta B"));
    expect(idxB).toBeLessThan(idxA);
  });

  it("filters rows by retriever (mmr)", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Pergunta A");
    // open the Retrievers filter and pick mmr from the listbox
    await user.click(screen.getAllByLabelText(/retrievers/i)[0]);
    const option = await screen.findByRole("option", { name: "mmr" });
    await user.click(option);
    // Only Pergunta B uses mmr
    expect(screen.queryByText("Pergunta A")).not.toBeInTheDocument();
    expect(screen.getByText("Pergunta B")).toBeInTheDocument();
  });

  it("filters rows by llm (ollama)", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findAllByText(/recursive/);
    await user.click(screen.getAllByLabelText(/llms/i)[0]);
    await user.click(await screen.findByRole("option", { name: "ollama" }));
    await waitFor(() => expect(screen.queryByText("Pergunta A")).not.toBeInTheDocument());
    expect(screen.getByText("Pergunta B")).toBeInTheDocument();
  });

  it("opens a modal with full pergunta and resposta when a row is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText(/Pergunta A/));
    expect(await screen.findByText("Detalhe do resultado")).toBeInTheDocument();
    // latency chip only renders inside the modal
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
    await user.click(await screen.findByRole("button", { name: /voltar aos experimentos/i }));
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
});
