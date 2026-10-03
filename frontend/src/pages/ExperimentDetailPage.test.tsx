import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor, within } from "@testing-library/react";
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

  it("shows the question type and bridge entities in the drawer", async () => {
    const base = (await client.getExperiment(7)).results[0];
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "done",
      results: [
        { ...base, question_type: "ponte", evidence_hops: [1, 2], bridge_entities: ["Parque", "Evento"] },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await user.click(await screen.findByText(/Pergunta A/));
    expect(await screen.findByText("Ponte")).toBeInTheDocument();
    expect(screen.getByText("Parque · Evento")).toBeInTheDocument();
  });

  it("shows which hops were retrieved and which are missing in the drawer", async () => {
    const base = (await client.getExperiment(7)).results[0];
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "done",
      results: [
        {
          ...base,
          scores: { context_all_hops: 0 },
          question_type: "ponte",
          evidence_hops: [1, 2, 3],
          hops_found: [
            { hop: 1, found: true },
            { hop: 2, found: false },
            { hop: 3, found: true },
          ],
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await user.click(await screen.findByText(/Pergunta A/));
    const drawer = await screen.findByRole("dialog", { name: "Detalhe do resultado" });
    expect(within(drawer).getByText("Saltos recuperados").nextElementSibling).toHaveTextContent(
      /^1, 3$/,
    );
    expect(within(drawer).getByText("Saltos faltantes").nextElementSibling).toHaveTextContent(
      /^2$/,
    );
    expect(within(drawer).getByText("Todos os saltos")).toBeInTheDocument();
  });

  describe("a GraphRAG combination", () => {
    beforeEach(async () => {
      const base = (await client.getExperiment(7)).results[0];
      vi.mocked(client.getExperiment).mockResolvedValue({
        id: 7,
        name: "kind-ember-89",
        status: "done",
        results: [
          {
            ...base,
            rag: "graph",
            graph_stats: {
              entities: 12, relations: 8, chunks: 30, lines: 40, failed_lines: 4, failed_chunks: 0,
            },
          },
        ],
      });
    });

    it("shows its Grafo de conhecimento stats on the ranking row", async () => {
      renderPage();
      const button = await screen.findByRole("button", { name: /ver respostas da combinação 1/i });
      const row = button.closest("tr")!;
      expect(row).toHaveTextContent("Grafo (GraphRAG)");
      expect(row).toHaveTextContent("12 entidades · 8 relações · 30 trechos · 10% das linhas com falha");
      // graph searches no Retriever.
      expect(within(row).getByTitle("Busca: —")).toBeInTheDocument();
    });

    it("shows the stats in the result drawer", async () => {
      renderPage();
      const user = userEvent.setup();
      await openAnswers(user);
      await user.click(await screen.findByText(/Pergunta A/));
      const drawer = await screen.findByRole("dialog", { name: "Detalhe do resultado" });
      expect(within(drawer).getByText("Grafo de conhecimento").nextElementSibling).toHaveTextContent(
        "12 entidades · 8 relações · 30 trechos · 10% das linhas com falha",
      );
    });
  });

  it("hides the hops when they were not matched", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await user.click(await screen.findByText(/Pergunta A/));
    const drawer = await screen.findByRole("dialog", { name: "Detalhe do resultado" });
    expect(within(drawer).queryByText("Saltos recuperados")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("Saltos faltantes")).not.toBeInTheDocument();
  });

  it("shows an unannotated question as a single-passage question", async () => {
    renderPage();
    const user = userEvent.setup();
    await openAnswers(user);
    await user.click(await screen.findByText(/Pergunta A/));
    const drawer = await screen.findByRole("dialog", { name: "Detalhe do resultado" });
    expect(within(drawer).getByText("Um trecho")).toBeInTheDocument();
  });

  describe("filter by Tipo de pergunta", () => {
    async function mockTyped() {
      const [a, b] = (await client.getExperiment(7)).results;
      // Pergunta A (simples) and Pergunta C (ponte) on combination A; Pergunta B (ponte) on B.
      vi.mocked(client.getExperiment).mockResolvedValue({
        id: 7,
        name: "kind-ember-89",
        status: "done",
        results: [
          a,
          { ...a, question: "Pergunta C", question_type: "ponte", scores: { answer_relevancy: 1, faithfulness: 1 } },
          { ...b, question_type: "ponte" },
        ],
      });
    }

    it("is hidden when every question has the same type", async () => {
      renderPage();
      await screen.findByRole("region", { name: /melhor combinação/i });
      expect(screen.queryByRole("radiogroup", { name: /tipo de pergunta/i })).not.toBeInTheDocument();
    });

    it("narrows the ranking and the answers to the chosen type", async () => {
      await mockTyped();
      renderPage();
      const user = userEvent.setup();
      const filter = await screen.findByRole("radiogroup", { name: /tipo de pergunta/i });
      // Over every question, combination B (0.85) beats A (mean of 0.30 and 1.0 = 0.65).
      expect(screen.getByRole("region", { name: /melhor combinação/i })).toHaveTextContent("Por tokens");

      await user.click(within(filter).getByRole("radio", { name: "Ponte" }));
      // Only ponte questions: A scores 1.0 on Pergunta C and wins.
      const winner = screen.getByRole("region", { name: /melhor combinação/i });
      expect(winner).toHaveTextContent("Recursivo");
      expect(winner).toHaveTextContent("Média 1.00");

      await openAnswers(user);
      expect(await screen.findByText("Pergunta C")).toBeInTheDocument();
      expect(screen.getByText("Pergunta B")).toBeInTheDocument();
      expect(screen.queryByText("Pergunta A")).not.toBeInTheDocument();
    });

    it("shows in the ranking the mean of each metric per type", async () => {
      await mockTyped();
      renderPage();
      const byType = await screen.findByRole("table", { name: /média de cada métrica por tipo/i });
      const ponte = within(byType).getByRole("row", { name: /ponte/i });
      // Ponte answers: Pergunta C (1.0, 1.0) and Pergunta B (0.9, 0.8).
      expect(ponte).toHaveTextContent("0.95"); // answer_relevancy
      expect(ponte).toHaveTextContent("0.90"); // faithfulness and média
      expect(within(byType).getByRole("row", { name: /um trecho/i })).toHaveTextContent("0.30");

      // Each combination also gets its média per type.
      const ranking = screen.getByRole("table", { name: /média de cada métrica por combinação/i });
      expect(within(ranking).getByRole("columnheader", { name: /média · ponte/i })).toBeInTheDocument();
    });

    it("drops the per-type columns once a single type is chosen", async () => {
      await mockTyped();
      renderPage();
      const user = userEvent.setup();
      const filter = await screen.findByRole("radiogroup", { name: /tipo de pergunta/i });
      await user.click(within(filter).getByRole("radio", { name: "Ponte" }));
      expect(screen.queryByRole("table", { name: /média de cada métrica por tipo/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: /média · ponte/i })).not.toBeInTheDocument();
    });

    it("goes back to the first page of answers when the type changes", async () => {
      const a = (await client.getExperiment(7)).results[0];
      const many = Array.from({ length: 12 }, (_, i) => ({ ...a, question: `Simples ${i}` }));
      vi.mocked(client.getExperiment).mockResolvedValue({
        id: 7, name: "kind-ember-89", status: "done",
        results: [...many, { ...a, question: "Só ponte", question_type: "ponte" }],
      });
      renderPage();
      const user = userEvent.setup();
      const filter = await screen.findByRole("radiogroup", { name: /tipo de pergunta/i });
      await openAnswers(user);
      await user.click(screen.getByRole("button", { name: "2" }));
      await user.click(within(filter).getByRole("radio", { name: "Ponte" }));
      expect(await screen.findByText("Só ponte")).toBeInTheDocument();
    });

    it("applies to the charts", async () => {
      await mockTyped();
      renderPage();
      const user = userEvent.setup();
      const filter = await screen.findByRole("radiogroup", { name: /tipo de pergunta/i });
      await user.click(within(filter).getByRole("radio", { name: "Ponte" }));
      await user.click(screen.getByRole("tab", { name: /gráficos/i }));
      expect((await screen.findAllByRole("button", { name: /^Pergunta C · / })).length).toBeGreaterThan(0);
      expect(screen.queryByRole("button", { name: /^Pergunta A · / })).not.toBeInTheDocument();
    });
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

  it("says the answers are being scored during the evaluation stage", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 9,
      name: "avaliando",
      status: "running",
      created_at: "2026-07-05T10:00:00.000Z",
      progress: { completed: 1, total: 1, phase: "evaluating" },
      results: [],
    });
    renderPage();
    expect(await screen.findByText("Avaliando as respostas")).toBeInTheDocument();
    expect(screen.queryByText(/1 de 1 combinações/)).not.toBeInTheDocument();
  });

  it("passes the evaluating phase through to the charts tab caption", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "kind-ember-89",
      status: "running",
      progress: { completed: 2, total: 2, phase: "evaluating" },
      results: [
        {
          chunking: "recursive", embedding: "gemini", rag: "naive", retriever: "similarity",
          llm: "gemini", question: "Pergunta A", answer: "Resposta A completa.",
          scores: { answer_relevancy: 0.2, faithfulness: 0.4 }, latency_ms: 100, tokens: 10,
        },
        {
          chunking: "token", embedding: "gemini", rag: "agentic", retriever: "mmr",
          llm: "ollama", question: "Pergunta B", answer: "Resposta B completa.",
          scores: { answer_relevancy: 0.9, faithfulness: 0.8 }, latency_ms: 200, tokens: 20,
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    expect((await screen.findAllByText(/parcial: avaliando as respostas\./i)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/de 2 combinações/i)).not.toBeInTheDocument();
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

  it("has a Gráficos tab whose focus survives switching tabs", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    await user.click(await screen.findByRole("radio", { name: "Só top" }));
    await openAnswers(user);
    await user.click(screen.getByRole("tab", { name: /gráficos/i }));
    expect(await screen.findByRole("radio", { name: "Só top" })).toBeChecked();
  });

  it("keeps the charts cost choice when switching tabs", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    await user.click(await screen.findByRole("radio", { name: "Tokens" }));
    await openAnswers(user);
    await user.click(screen.getByRole("tab", { name: /gráficos/i }));
    expect(await screen.findByRole("radio", { name: "Tokens" })).toBeChecked();
  });

  it("opens the result drawer from the charts matrix", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    await user.click(await screen.findByRole("button", { name: /^Pergunta A · #2:/ }));
    expect(await screen.findByText("Detalhe do resultado")).toBeInTheDocument();
  });
});
