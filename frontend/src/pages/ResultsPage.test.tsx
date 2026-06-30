import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ResultsPage } from "./ResultsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ResultsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listExperiments).mockResolvedValue([
    { id: 7, name: "kind-ember-89", status: "done" },
  ]);
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
        question: "Onde fica o centro?",
        answer: "Na Praça da Matriz, segundo o guia da cidade.",
        scores: { answer_relevancy: 0.66, faithfulness: 0.75 },
        latency_ms: 14000,
        tokens: 25,
      },
    ],
  });
});

describe("ResultsPage", () => {
  it("loads an experiment and shows its results, expanding a row on click", async () => {
    renderPage();
    const user = userEvent.setup();
    // first experiment auto-selected or chosen
    const row = await screen.findByText(/Onde fica o centro/);
    await user.click(row);
    expect(await screen.findByText(/Praça da Matriz/)).toBeInTheDocument();
    expect(screen.getByText(/14000/)).toBeInTheDocument();
  });
});
