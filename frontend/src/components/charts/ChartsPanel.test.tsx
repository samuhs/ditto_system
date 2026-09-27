import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
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
    mediaMark(8)!.focus();
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
