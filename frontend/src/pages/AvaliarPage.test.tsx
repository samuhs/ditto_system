import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { AnnotationQueue, Rubric } from "../api/types";
import { AvaliarPage } from "./AvaliarPage";

vi.mock("../api/client");

const rubric: Rubric = {
  version: 1,
  dimensions: [
    {
      key: "correctness", label: "Correção", question: "A resposta está certa?",
      levels: [
        { value: 0, label: "Errada", description: "Errada." },
        { value: 1, label: "Parcial", description: "Parcial." },
        { value: 2, label: "Correta", description: "Correta e completa." },
      ],
    },
    {
      key: "grounding", label: "Fundamentação", question: "Está nos trechos?",
      levels: [
        { value: 0, label: "Inventa", description: "Inventa." },
        { value: 1, label: "Parcial", description: "Parcial." },
        { value: 2, label: "Apoiada", description: "Apoiada." },
      ],
    },
  ],
};

const round = {
  id: 5, name: "piloto", description: "", status: "open" as const, seed: 7, rubric_version: 1,
  experiment_ids: [90], size: 2, pilot: false, strata: [], allocation: "proportional" as const,
  created_at: null,
};

function queue(over: Partial<AnnotationQueue> = {}): AnnotationQueue {
  return {
    round,
    annotator: { id: 3, name: "Ana" },
    items: [
      {
        id: 11, position: 0, question: "Quantos metros tem a roda-gigante?", question_type: "simples",
        reference_answer: "42 metros.", evidence: ["A roda tem 42 metros de altura"],
        retrieved_context: ["Trecho recuperado sobre a roda"], generated_answer: "Tem 42 metros.",
        note: null,
      },
      {
        id: 12, position: 1, question: "Quanto custa o almoço?", question_type: "simples",
        reference_answer: "R$ 3.", evidence: ["almoço por R$ 3"], retrieved_context: [],
        generated_answer: "Custa R$ 3.", note: null,
      },
    ],
    done: 0,
    total: 2,
    ...over,
  };
}

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/anotar"]}>
        <Routes>
          <Route path="/anotar" element={<AvaliarPage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("AvaliarPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.listAnnotators).mockResolvedValue([{ id: 3, name: "Ana", active: true }]);
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([round]);
    vi.mocked(client.getRubric).mockResolvedValue(rubric);
    vi.mocked(client.getAnnotationQueue).mockResolvedValue(queue());
    vi.mocked(client.saveAnnotationNote).mockResolvedValue({
      item_id: 11, annotator_id: 3, correctness: 2, grounding: 2,
    });
  });

  it("starts by asking who is evaluating, with a way to register a new Avaliador", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: "Ana" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sou um avaliador novo/i })).toBeInTheDocument();
  });

  it("registers a new Avaliador and moves on to choosing the Rodada", async () => {
    vi.mocked(client.createAnnotator).mockResolvedValue({ id: 9, name: "Bruno", active: true });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /sou um avaliador novo/i }));

    await userEvent.type(screen.getByLabelText(/seu nome/i), "Bruno");
    await userEvent.click(screen.getByRole("button", { name: /começar/i }));

    expect(client.createAnnotator).toHaveBeenCalledWith("Bruno");
    expect(await screen.findByRole("button", { name: /piloto/i })).toBeInTheDocument();
    expect(screen.getByText(/Bruno/)).toBeInTheDocument();
  });

  it("shows the API error when the name is already taken", async () => {
    vi.mocked(client.createAnnotator).mockRejectedValue(new Error("Já existe um avaliador chamado Ana."));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /sou um avaliador novo/i }));

    await userEvent.type(screen.getByLabelText(/seu nome/i), "ana");
    await userEvent.click(screen.getByRole("button", { name: /começar/i }));

    expect(await screen.findByText(/Já existe um avaliador chamado Ana/)).toBeInTheDocument();
  });

  it("only offers open Rodadas", async () => {
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([
      round, { ...round, id: 6, name: "antiga", status: "closed" },
    ]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));

    expect(await screen.findByRole("button", { name: /piloto/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /antiga/i })).not.toBeInTheDocument();
  });

  async function openRound() {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));
    await userEvent.click(await screen.findByRole("button", { name: /piloto/i }));
    await screen.findByText("Quantos metros tem a roda-gigante?");
  }

  it("shows one answer at a time with the reference, the evidence and the progress", async () => {
    await openRound();

    expect(client.getAnnotationQueue).toHaveBeenCalledWith(5, 3);
    expect(screen.getByText("42 metros.")).toBeInTheDocument();
    expect(screen.getByText("A roda tem 42 metros de altura")).toBeInTheDocument();
    expect(screen.getByText("Tem 42 metros.")).toBeInTheDocument();
    expect(screen.getByText(/0 de 2 avaliadas/i)).toBeInTheDocument();
    expect(screen.queryByText("Quanto custa o almoço?")).not.toBeInTheDocument();
  });

  it("saves the two notes and moves to the next answer", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Fundamentação: 1 · Parcial/ }));
    await userEvent.click(screen.getByRole("button", { name: /salvar e seguir/i }));

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(11, 3, { correctness: 2, grounding: 1 });
    expect(await screen.findByText("Quanto custa o almoço?")).toBeInTheDocument();
    expect(screen.getByText(/1 de 2 avaliadas/i)).toBeInTheDocument();
  });

  it("after saving, comes back to an answer skipped earlier", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("button", { name: /próxima/i }));
    await screen.findByText("Quanto custa o almoço?");

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Fundamentação: 2 · Apoiada/ }));
    await userEvent.click(screen.getByRole("button", { name: /salvar e seguir/i }));

    expect(await screen.findByText("Quantos metros tem a roda-gigante?")).toBeInTheDocument();
  });

  it("does not save until both dimensions have a note", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));

    expect(screen.getByRole("button", { name: /salvar e seguir/i })).toBeDisabled();
  });

  it("shows a note already given when the Avaliador comes back to an answer", async () => {
    vi.mocked(client.getAnnotationQueue).mockResolvedValue(queue({
      items: queue().items.map((i) => (i.id === 11 ? { ...i, note: { correctness: 1, grounding: 2 } } : i)),
      done: 1,
    }));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));
    await userEvent.click(await screen.findByRole("button", { name: /piloto/i }));

    // Opens on the first answer still without a note, then goes back to the one already scored.
    expect(await screen.findByText("Quanto custa o almoço?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /anterior/i }));

    expect(await screen.findByText("Quantos metros tem a roda-gigante?")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Correção: 1 · Parcial/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Fundamentação: 2 · Apoiada/ })).toBeChecked();
  });

  it("never shows which technique or LLM produced the answer", async () => {
    await openRound();

    expect(screen.queryByText(/naive|agentic|compression|qwen|gemma|tucano/i)).not.toBeInTheDocument();
  });

  it("goes back to the identification when the Avaliador leaves", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("button", { name: /sair/i }));

    expect(await screen.findByRole("button", { name: /sou um avaliador novo/i })).toBeInTheDocument();
    expect(screen.queryByText("Quantos metros tem a roda-gigante?")).not.toBeInTheDocument();
  });

  it("says when the whole Rodada is done", async () => {
    vi.mocked(client.getAnnotationQueue).mockResolvedValue(queue({
      items: queue().items.map((i) => ({ ...i, note: { correctness: 2, grounding: 2 } })),
      done: 2,
    }));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));
    await userEvent.click(await screen.findByRole("button", { name: /piloto/i }));

    await waitFor(() => expect(screen.getByText(/2 de 2 avaliadas/i)).toBeInTheDocument());
  });
});
