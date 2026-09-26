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
  hit_rate: 0.5,
  with_evidence: { chrf: 0.9 },
  without_evidence: { chrf: 0.2 },
  ...extra,
});

beforeEach(() => {
  vi.mocked(client.getExperimentDifficulty).mockResolvedValue({
    llms: ["qwen3:1.7b"],
    metrics: ["chrf", "context_hit"],
    questions: [
      { question: "Fácil?", signals: { negation: 0 }, retrieval_signals: {}, by_llm: { "qwen3:1.7b": cell(0.8) } },
      { question: "Difícil?", signals: { negation: 1, out_of_corpus: 0.25 }, retrieval_signals: { top_score: 0.71 }, by_llm: { "qwen3:1.7b": cell(0.1) } },
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
  });

  it("opens the question's signals", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Difícil?" }));
    expect(await screen.findByText("Tem negação")).toBeInTheDocument();
    expect(screen.getByText("sim")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("Nota do melhor trecho")).toBeInTheDocument();
  });
});
