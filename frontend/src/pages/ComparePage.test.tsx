import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
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

beforeEach(() => {
  vi.mocked(client.getComparison).mockResolvedValue(comparison);
});

describe("ComparePage", () => {
  it("asks the API for the items, Linha de base and metric in the URL", async () => {
    renderPage("/compare?items=25:3,37:12&baseline=25:3&metric=answer_correctness");
    await screen.findByText("Qwen3.5-4B");
    expect(client.getComparison).toHaveBeenCalledWith(["25:3", "37:12"], "25:3", "answer_correctness");
  });

  it("shows each item's difference against the Linha de base with its CI", async () => {
    renderPage("/compare?items=25:3,37:12");
    const row = (await screen.findByText("Qwen3.5-4B")).closest("tr")!;
    expect(within(row).getByText("+0.089")).toBeInTheDocument();
    expect(within(row).getByText("[0.041, 0.137]")).toBeInTheDocument();
    expect(within(row).getByLabelText("significativa")).toBeInTheDocument();
    expect(within(row).getByText("parcial")).toBeInTheDocument();
    expect(within(row).getByText("34")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /fase-3/ })).toHaveAttribute("href", "/results/37");
    const baseline = screen.getByText("Qwen2.5-3B").closest("tr")!;
    expect(within(baseline).getByText("Linha de base")).toBeInTheDocument();
  });

  it("shows a metric an item lacks as missing, not zero", async () => {
    renderPage("/compare?items=25:3,37:12");
    const row = (await screen.findByText("Qwen3.5-4B")).closest("tr")!;
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

  it("shows the API's error", async () => {
    vi.mocked(client.getComparison).mockRejectedValue(new Error("Experimento 999 não existe"));
    renderPage("/compare?items=999:1");
    expect(await screen.findByText(/Experimento 999 não existe/)).toBeInTheDocument();
  });
});
