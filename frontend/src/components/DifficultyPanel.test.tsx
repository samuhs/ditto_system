import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DifficultyPanel } from "./DifficultyPanel";

vi.mock("../api/client");

const cell = (mean: number, extra = {}) => ({
  retrieval: { chrf: { mean, std: 0.1, n: 3 } },
  closed_book: { chrf: 0.05 },
  oracle: { chrf: 0.95 },
  hit_rate: 0.5,
  with_evidence: { chrf: 0.9 },
  without_evidence: { chrf: 0.2 },
  ...extra,
});

beforeEach(() => {
  vi.mocked(client.getExperimentDifficulty).mockResolvedValue({
    llms: ["qwen3:1.7b"],
    metrics: ["chrf", "context_hit"],
    metric: "chrf",
    irt: {
      metric: "chrf",
      n_questions: 2,
      n_configurations: 3,
      reliable: false,
      min_questions: 50,
      difficulty: { "Fácil?": -1.2, "Difícil?": 1.2 },
      difficulty_by_llm: { "qwen3:1.7b": { "Fácil?": -1.0, "Difícil?": 1.0 } },
      ability: {},
    },
    perplexity_skipped: { "qwen3:1.7b": { free_mb: 1107, needed_mb: 2178 } },
    correlations: {
      n_questions: 2,
      reliable: false,
      rows: [
        { signal: "negation", kind: "question", overall: 0.8, by_llm: { "qwen3:1.7b": 0.9 } },
        { signal: "perplexity", kind: "model", overall: null, by_llm: { "qwen3:1.7b": 0.5 } },
        { signal: "yes_no", kind: "question", overall: null, by_llm: { "qwen3:1.7b": null } },
      ],
    },
    questions: [
      { question: "Fácil?", signals: { negation: 0 }, retrieval_signals: {}, model_signals: {}, by_llm: { "qwen3:1.7b": cell(0.8) } },
      { question: "Difícil?", signals: { negation: 1, out_of_corpus: 0.25 }, retrieval_signals: { top_score: 0.71 }, model_signals: { "qwen3:1.7b": { perplexity: 42.5 } }, by_llm: { "qwen3:1.7b": cell(0.1) } },
    ],
  });
});

function renderPanel() {
  return render(
    <MantineProvider>
      <DifficultyPanel experimentId={7} />
    </MantineProvider>,
  );
}

describe("DifficultyPanel", () => {
  it("lists the hardest question first with closed-book and evidence columns", async () => {
    renderPanel();
    const rows = await screen.findAllByRole("row");
    expect(rows[2]).toHaveTextContent("Difícil?");
    expect(rows[3]).toHaveTextContent("Fácil?");
    expect(screen.getAllByText("Sem busca").length).toBeGreaterThan(0);
    expect(within(rows[2]).getByText("50%")).toBeInTheDocument();
    expect(within(rows[2]).getByText("+1.20")).toBeInTheDocument();
    expect(screen.getAllByText("Oráculo").length).toBeGreaterThan(0);
    expect(screen.getByText("TRI só indicativa")).toBeInTheDocument();
  });

  it("refetches the IRT fit when the metric changes", async () => {
    const base = await client.getExperimentDifficulty(7);
    // The API answers with the metric it was asked for.
    vi.mocked(client.getExperimentDifficulty).mockImplementation(async (_id, metric) => ({
      ...base,
      metric: metric ?? "chrf",
    }));
    renderPanel();
    const user = userEvent.setup();
    await screen.findAllByRole("row");
    await user.click(screen.getByRole("textbox", { name: "Métrica" }));
    await user.click(await screen.findByRole("option", { name: /acerto da busca/i }));
    expect(client.getExperimentDifficulty).toHaveBeenLastCalledWith(7, "context_hit");
  });

  it("explains how to read the table in a pop-up", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /como ler esta tabela/i }));
    expect(await screen.findByText("Como ler a dificuldade por pergunta")).toBeInTheDocument();
    expect(screen.getByText(/piso → seu sistema → teto/)).toBeInTheDocument();
  });

  it("shows which answer-free signals predict difficulty", async () => {
    renderPanel();
    const table = (await screen.findByText("Quais sinais preveem a dificuldade")).closest("section")!;
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + two signals; the all-empty one is hidden
    expect(rows[1]).toHaveTextContent("Tem negação");
    expect(rows[1]).toHaveTextContent("+0.80");
    expect(rows[2]).toHaveTextContent("Perplexidade da pergunta no modelo");
    expect(screen.getByText("Perplexidade não calculada para qwen3:1.7b")).toBeInTheDocument();
    expect(screen.getByText(/Havia 1107 MB/)).toBeInTheDocument();
  });

  it("opens the question's signals", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Difícil?" }));
    const drawer = within(await screen.findByRole("dialog"));
    expect(drawer.getByText("Tem negação")).toBeInTheDocument();
    expect(drawer.getByText("sim")).toBeInTheDocument();
    expect(drawer.getByText("25%")).toBeInTheDocument();
    expect(drawer.getByText("Nota do melhor trecho")).toBeInTheDocument();
    expect(drawer.getByText(/Dificuldade estimada/)).toBeInTheDocument();
    expect(drawer.getByText("Perplexidade da pergunta no modelo")).toBeInTheDocument();
    expect(drawer.getByText("42.5")).toBeInTheDocument();
  });
});
