import { MantineProvider } from "@mantine/core";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExperimentResultRow } from "../../api/types";
import { rankByMedia, rankCombinations } from "../../experiments/ranking";
import { DEFAULT_FOCUS, type FocusState } from "./aggregate";
import { ChartsPanel } from "./ChartsPanel";
import { fixture } from "./testFixture";

const onShowAnswers = vi.fn();
const onOpenRow = vi.fn();

function Harness({
  results = fixture(),
  initial = DEFAULT_FOCUS,
  partial = null,
}: {
  results?: ExperimentResultRow[];
  initial?: FocusState;
  partial?: { completed: number; total: number } | null;
}) {
  const [focus, setFocus] = useState(initial);
  const metricKeys = [...new Set(results.flatMap((r) => Object.keys(r.scores)))].sort();
  const ranked = rankByMedia(rankCombinations(results, metricKeys));
  return (
    <ChartsPanel
      results={results} metricKeys={metricKeys} ranked={ranked}
      focus={focus} onFocusChange={setFocus} partial={partial}
      onShowAnswers={onShowAnswers} onOpenRow={onOpenRow}
    />
  );
}

function renderPanel(props: Parameters<typeof Harness>[0] = {}) {
  return render(
    <MantineProvider>
      <Harness {...props} />
    </MantineProvider>,
  );
}

const mediaMark = (place: number) => screen.queryByRole("button", { name: new RegExp(`^#${place} Média `) });

beforeEach(() => {
  onShowAnswers.mockReset();
  onOpenRow.mockReset();
});

describe("ChartsPanel · focus and figure 1", () => {
  it("shows top 3 and bottom 3 by default", () => {
    renderPanel();
    for (const p of [1, 2, 3, 6, 7, 8]) expect(mediaMark(p)).toBeInTheDocument();
    expect(mediaMark(4)).not.toBeInTheDocument();
    expect(mediaMark(1)).toHaveAttribute("data-group", "top");
    expect(mediaMark(8)).toHaveAttribute("data-group", "bottom");
  });

  it("switching to top only drops the bottom", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("radio", { name: "Só top" }));
    expect(mediaMark(8)).not.toBeInTheDocument();
    expect(mediaMark(3)).toBeInTheDocument();
  });

  it("changing N changes the marks", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getAllByLabelText("N")[0]);
    await user.click(await screen.findByRole("option", { name: "1" }));
    expect(mediaMark(2)).not.toBeInTheDocument();
    expect(mediaMark(1)).toBeInTheDocument();
    expect(mediaMark(8)).toBeInTheDocument();
  });

  it("a manual pick joins as its own group", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getAllByLabelText("Adicionar combinações")[0]);
    await user.click(await screen.findByRole("option", { name: /^#4 / }));
    expect(mediaMark(4)).toHaveAttribute("data-group", "manual");
  });

  it("clicking or pressing Enter on a mark shows that combination's answers", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(mediaMark(1)!);
    expect(onShowAnswers).toHaveBeenCalledWith(
      expect.objectContaining({ chunking: "token", rag: "agentic", llm: "gemma" }),
    );
    act(() => {
      mediaMark(8)!.focus();
    });
    await user.keyboard("{Enter}");
    expect(onShowAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ chunking: "recursive", rag: "naive", llm: "qwen" }),
    );
  });

  it("falls back to Média when the chosen metric is gone", () => {
    renderPanel({ initial: { ...DEFAULT_FOCUS, metric: "context_recall" } });
    expect(screen.getAllByLabelText("Métrica dos gráficos")[0]).toHaveValue("Média");
  });

  it("marks partial results in the captions", () => {
    renderPanel({ partial: { completed: 3, total: 8 } });
    expect(screen.getAllByText(/parcial: 3 de 8 combinações/i).length).toBeGreaterThan(0);
  });

  it("has a screen-reader table for figure 1", () => {
    renderPanel();
    const table = screen.getByRole("table", { name: /figura 1/i });
    expect(within(table).getAllByRole("row").length).toBe(4); // header + 2 metrics + média
  });
});

describe("ChartsPanel · figures 2 and 3", () => {
  it("orders dimension panels by effect and lists fixed ones", () => {
    renderPanel();
    const panels = screen.getAllByRole("region", { name: /: efeito/ }).map((p) => p.getAttribute("aria-label"));
    expect(panels).toEqual(["Corte: efeito 0.40", "Técnica de RAG: efeito 0.20", "Modelo (LLM): efeito 0.10"]);
    expect(screen.getByText(/fixo neste experimento: embedding .*, busca /i)).toBeInTheDocument();
    expect(screen.queryByText(/grade incompleta/i)).not.toBeInTheDocument();
  });

  it("warns about an incomplete grid", () => {
    renderPanel({ results: fixture().filter((r) => !(r.chunking === "recursive" && r.rag === "naive" && r.llm === "qwen")) });
    expect(screen.getByText(/grade incompleta/i)).toBeInTheDocument();
  });

  it("rings the Pareto frontier, focused or not", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /^#2 Latência.*fronteira de Pareto/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^#3 Latência.*fronteira de Pareto/ })).not.toBeInTheDocument();
    const table = screen.getByRole("table", { name: /figura 3/i });
    const row5 = within(table).getAllByRole("row").find((r) => r.textContent?.startsWith("#5"));
    expect(row5).toHaveTextContent("sim");
  });

  it("falls back to tokens when latency is missing, and to a note when both are", () => {
    const noLatency = fixture().map((r) => ({ ...r, latency_ms: 0 }));
    const { unmount } = renderPanel({ results: noLatency });
    expect(screen.getAllByText("Tokens médios").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Latência média (ms)")).toHaveLength(0);
    unmount();
    renderPanel({ results: noLatency.map((r) => ({ ...r, tokens: 0 })) });
    expect(screen.getByText(/sem dados de custo neste experimento/i)).toBeInTheDocument();
  });

  it("needs at least two combinations for figures 2 and 3", () => {
    renderPanel({ results: fixture().slice(0, 2) });
    expect(screen.getAllByText(/precisa de ao menos 2 combinações/i)).toHaveLength(2);
    expect(mediaMark(1)).toBeInTheDocument();
  });
});

describe("ChartsPanel · figure 4", () => {
  it("lists questions hardest first", () => {
    renderPanel({ initial: { ...DEFAULT_FOCUS, metric: "faithfulness" } });
    const table = screen.getByRole("table", { name: /figura 4b/i });
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "Pergunta difícil",
      "Pergunta fácil",
    ]);
  });

  it("clicking a cell opens that answer", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /^Pergunta difícil · #1:/ }));
    expect(onOpenRow).toHaveBeenCalledWith(
      expect.objectContaining({ question: "Pergunta difícil", chunking: "token", rag: "agentic", llm: "gemma" }),
    );
  });

  it("a distribution mark shows the combination's answers", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /^#1 mediana/ }));
    expect(onShowAnswers).toHaveBeenCalledWith(expect.objectContaining({ llm: "gemma", chunking: "token" }));
  });

  it("shows a missing answer as an empty cell", () => {
    const results = fixture().filter(
      (r) => !(r.chunking === "token" && r.rag === "agentic" && r.llm === "gemma" && r.question === "Pergunta fácil"),
    );
    renderPanel({ results });
    expect(screen.getByLabelText("sem resposta")).toBeInTheDocument();
  });

  it("shows a row without metrics as a dash, not NaN", () => {
    const results = fixture();
    const i = results.findIndex((r) => r.chunking === "token" && r.rag === "agentic" && r.llm === "gemma");
    results[i] = { ...results[i], scores: {} };
    renderPanel({ results });
    expect(document.body.innerHTML).not.toContain("NaN");
  });
});
