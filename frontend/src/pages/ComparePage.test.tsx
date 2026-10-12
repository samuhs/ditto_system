import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { Comparison, ComparisonItem } from "../api/types";
import { ComparePage } from "./ComparePage";

vi.mock("../api/client");

function renderPage(url: string) {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/compare" element={<ComparePage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

function item(over: Partial<ComparisonItem>): ComparisonItem {
  return {
    id: "25:3", experiment_id: 25, experiment_name: "fase-1", run_id: 3, base: "guia",
    chunking: "markdown", embedding: "e5", rag: "naive", retriever: "similarity",
    llm: "Qwen2.5-3B", partial: false, n: 36,
    means: { answer_correctness: 0.512, context_hit: 0.9 }, diff: null,
    ...over,
  };
}

const comparison: Comparison = {
  other_bases: [],
  friedman: { chi2: 33.34, df: 7, p: 0.0000229, n: 36 },
  by_type: {
    types: ["simples", "ponte"],
    rows: [{
      id: "37:12",
      cells: {
        simples: { mean: 0.12, low: 0.05, high: 0.2, significant: true, n: 20 },
        ponte: null,
      },
    }],
  },
  baseline: "25:3",
  metric: "answer_correctness",
  metrics: ["answer_correctness", "context_hit"],
  base: "guia",
  items: [
    item({}),
    item({
      id: "37:12", experiment_id: 37, experiment_name: "fase-3", run_id: 12, llm: "Qwen3.5-4B",
      partial: true, n: 34, means: { answer_correctness: 0.601, context_hit: null },
      diff: { mean: 0.089, low: 0.041, high: 0.137, significant: true },
    }),
  ],
  excluded: [{ id: "40:1", reason: "nenhuma pergunta em comum com a Linha de base" }],
};

/** The paired table (the by-type table repeats the Combinações). */
async function mainTable() {
  return within(await screen.findByRole("table", { name: /métrica principal/i }));
}

beforeEach(() => {
  vi.mocked(client.getComparison).mockResolvedValue(comparison);
  vi.mocked(client.listBases).mockResolvedValue([
    { name: "guia", indexes: [], in_use: null }, { name: "faq", indexes: [], in_use: null },
  ]);
  vi.mocked(client.listExperiments).mockResolvedValue({
    items: [{ id: 37, name: "fase-3", status: "done", base: "guia", created_at: "2026-10-10T00:00:00+00:00" }],
    total: 1, page: 1, page_size: 100,
  });
  vi.mocked(client.getExperiment).mockResolvedValue({
    id: 37, name: "fase-3", status: "done", results: [],
    runs: [
      { id: 12, chunking: "markdown", embedding: "e5", rag: "naive", retriever: "similarity", llm: "Qwen3.5-4B", status: "done" },
      { id: 13, chunking: "markdown", embedding: "e5", rag: "agentic", retriever: "similarity", llm: "Qwen3.5-4B", status: "done" },
    ],
  } as Awaited<ReturnType<typeof client.getExperiment>>);
});

function lastComparisonCall() {
  const calls = vi.mocked(client.getComparison).mock.calls;
  return calls[calls.length - 1];
}

describe("ComparePage", () => {
  it("asks the API for the items, Linha de base and metric in the URL", async () => {
    renderPage("/compare?items=25:3,37:12&baseline=25:3&metric=answer_correctness");
    await mainTable();
    expect(client.getComparison).toHaveBeenCalledWith(["25:3", "37:12"], "25:3", "answer_correctness");
  });

  it("shows each item's difference against the Linha de base with its CI", async () => {
    renderPage("/compare?items=25:3,37:12");
    const table = await mainTable();
    const row = table.getByText("Qwen3.5-4B").closest("tr")!;
    expect(within(row).getByText("+0.089")).toBeInTheDocument();
    expect(within(row).getByText("[0.041, 0.137]")).toBeInTheDocument();
    expect(within(row).getByLabelText("significativa")).toBeInTheDocument();
    expect(within(row).getByText("parcial")).toBeInTheDocument();
    expect(within(row).getByText("34")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /fase-3/ })).toHaveAttribute("href", "/results/37");
    const baseline = table.getByText("Qwen2.5-3B").closest("tr")!;
    expect(within(baseline).getByText("Linha de base")).toBeInTheDocument();
  });

  it("shows a metric an item lacks as missing, not zero", async () => {
    renderPage("/compare?items=25:3,37:12");
    const row = (await mainTable()).getByText("Qwen3.5-4B").closest("tr")!;
    expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("lists the items left out and why", async () => {
    renderPage("/compare?items=25:3,37:12,40:1");
    expect(await screen.findByText(/nenhuma pergunta em comum/)).toBeInTheDocument();
    expect(screen.getByText(/40:1/)).toBeInTheDocument();
  });

  it("says how to start when the URL has no items", async () => {
    renderPage("/compare");
    expect(await screen.findByText(/nenhuma combinação escolhida/i)).toBeInTheDocument();
    expect(client.getComparison).not.toHaveBeenCalled();
  });

  it("shows Friedman's test with the questions it used", async () => {
    renderPage("/compare?items=25:3,37:12");
    expect(await screen.findByText(/χ² = 33\.34/)).toHaveTextContent(
      "Friedman: χ² = 33.34, 7 graus de liberdade, p < 0.001, sobre 36 perguntas",
    );
    expect(screen.getByText(/sem correção para comparações múltiplas/i)).toBeInTheDocument();
  });

  it("says why Friedman's test is missing", async () => {
    vi.mocked(client.getComparison).mockResolvedValue({
      ...comparison, friedman: { reason: "o teste precisa de ao menos duas Combinações pareadas" },
    });
    renderPage("/compare?items=25:3");
    expect(await screen.findByText(/Friedman não calculado: o teste precisa/)).toBeInTheDocument();
  });

  it("shows the difference by Tipo de pergunta", async () => {
    renderPage("/compare?items=25:3,37:12");
    const table = await screen.findByRole("table", { name: /por tipo de pergunta/i });
    expect(within(table).getByRole("columnheader", { name: "Um trecho" })).toBeInTheDocument();
    const row = within(table).getByText("Qwen3.5-4B").closest("tr")!;
    expect(within(row).getByText("+0.120")).toBeInTheDocument();
    expect(within(row).getByText("n = 20")).toBeInTheDocument();
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("shows items of another Base apart, with their own mean and CI", async () => {
    const { diff: _diff, ...rest } = item({ id: "50:2", experiment_id: 50, experiment_name: "faq-1", base: "faq", llm: "Gemma-4-E2B", n: 40 });
    vi.mocked(client.getComparison).mockResolvedValue({
      ...comparison, other_bases: [{ ...rest, mean: { mean: 0.44, low: 0.38, high: 0.5 } }],
    });
    renderPage("/compare?items=25:3,37:12,50:2");
    const table = await screen.findByRole("table", { name: /outras bases/i });
    const row = within(table).getByText("Gemma-4-E2B").closest("tr")!;
    expect(within(row).getByText("faq")).toBeInTheDocument();
    expect(within(row).getByText("[0.380, 0.500]")).toBeInTheDocument();
    expect(within(row).getByText("40")).toBeInTheDocument();
  });

  it("adds Combinações picked by Base, then Experimento", async () => {
    const user = userEvent.setup();
    renderPage("/compare");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Base" }), "guia");
    expect(client.listExperiments).toHaveBeenCalledWith(1, 100, "guia");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Experimento" }), "37");
    await user.click(await screen.findByRole("checkbox", { name: /Simples.*Qwen3\.5-4B/ }));
    await waitFor(() => expect(lastComparisonCall()).toEqual([["37:12"], null, null]));
  });

  it("removes an item", async () => {
    const user = userEvent.setup();
    renderPage("/compare?items=25:3,37:12");
    const row = (await mainTable()).getByText("Qwen3.5-4B").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: /remover/i }));
    await waitFor(() => expect(lastComparisonCall()).toEqual([["25:3"], null, null]));
  });

  it("removing the Linha de base falls back to the first item", async () => {
    const user = userEvent.setup();
    renderPage("/compare?items=25:3,37:12&baseline=25:3");
    const row = (await mainTable()).getByText("Qwen2.5-3B").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: /remover/i }));
    await waitFor(() => expect(lastComparisonCall()).toEqual([["37:12"], null, null]));
  });

  it("makes any row the Linha de base", async () => {
    const user = userEvent.setup();
    renderPage("/compare?items=25:3,37:12");
    const row = (await mainTable()).getByText("Qwen3.5-4B").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: /usar como linha de base/i }));
    await waitFor(() => expect(lastComparisonCall()).toEqual([["25:3", "37:12"], "37:12", null]));
  });

  it("changes the main metric", async () => {
    const user = userEvent.setup();
    renderPage("/compare?items=25:3,37:12");
    await mainTable();
    await user.selectOptions(screen.getByRole("combobox", { name: /métrica principal/i }), "context_hit");
    await waitFor(() => expect(lastComparisonCall()).toEqual([["25:3", "37:12"], null, "context_hit"]));
  });

  it("exports the Comparação it shows as CSV and LaTeX", async () => {
    vi.mocked(client.comparisonExportUrl).mockImplementation(
      (format, items, baseline, metric) => `/api/export.${format}?${items.join(",")}|${baseline}|${metric}`,
    );
    renderPage("/compare?items=25:3,37:12&baseline=37:12");
    await mainTable();
    expect(screen.getByRole("link", { name: /exportar csv/i })).toHaveAttribute(
      "href", "/api/export.csv?25:3,37:12|37:12|answer_correctness",
    );
    expect(screen.getByRole("link", { name: /exportar latex/i })).toHaveAttribute(
      "href", "/api/export.tex?25:3,37:12|37:12|answer_correctness",
    );
  });

  it("shows the API's error", async () => {
    vi.mocked(client.getComparison).mockRejectedValue(new Error("Experimento 999 não existe"));
    renderPage("/compare?items=999:1");
    expect(await screen.findByText(/Experimento 999 não existe/)).toBeInTheDocument();
  });
});
