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
    { id: 8, name: "swift-fox-12", status: "pending" },
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
  it("shows experiment list without detail panel on load", async () => {
    renderPage();
    expect(await screen.findByText("kind-ember-89")).toBeInTheDocument();
    expect(screen.getByText("swift-fox-12")).toBeInTheDocument();
    expect(screen.queryByLabelText(/fechar painel/i)).not.toBeInTheDocument();
  });

  it("opens detail panel and loads results when experiment is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    expect(await screen.findByLabelText(/fechar painel/i)).toBeInTheDocument();
    expect(await screen.findByText(/Onde fica o centro/)).toBeInTheDocument();
  });

  it("closes detail panel when X button is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    await screen.findByLabelText(/fechar painel/i);
    await user.click(screen.getByLabelText(/fechar painel/i));
    expect(screen.queryByLabelText(/fechar painel/i)).not.toBeInTheDocument();
  });

  it("expands a result row on click inside the detail panel", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    const row = await screen.findByText(/Onde fica o centro/);
    await user.click(row);
    expect(await screen.findByText(/Praça da Matriz/)).toBeInTheDocument();
    expect(screen.getByText(/14000/)).toBeInTheDocument();
  });
});
