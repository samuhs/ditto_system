import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  experiment_ids: [90], size: 2, pilot: false, strata: [], allocation: "proportional" as const, adjudicator_id: null, source_round_id: null, retest_annotator_id: null,
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
        grounding_applicable: true, note: null,
      },
      {
        id: 12, position: 1, question: "Quanto custa o almoço?", question_type: "simples",
        reference_answer: "R$ 3.", evidence: ["almoço por R$ 3"], retrieved_context: [],
        generated_answer: "Custa R$ 3.", grounding_applicable: false, note: null,
      },
    ],
    done: 0,
    total: 2,
    ...over,
  };
}

function note(correctness: number | null, grounding: number | null) {
  return { correctness, grounding, cannot_evaluate: false, reason: null, comment: null };
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
    vi.mocked(client.joinAnnotationRound).mockResolvedValue(undefined);
    vi.mocked(client.saveAnnotationNote).mockResolvedValue({
      item_id: 11, annotator_id: 3, ...note(2, 2),
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

  it("joins the Rodada when the Avaliador picks it", async () => {
    await openRound();

    expect(client.joinAnnotationRound).toHaveBeenCalledWith(5, 3);
  });

  it("marks pilot Rodadas in the choice", async () => {
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([{ ...round, pilot: true }]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));

    expect(await screen.findByRole("button", { name: /piloto · 2 respostas · rodada piloto/i })).toBeInTheDocument();
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

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(11, 3, note(2, 1));
    expect(await screen.findByText("Quanto custa o almoço?")).toBeInTheDocument();
    expect(screen.getByText(/1 de 2 avaliadas/i)).toBeInTheDocument();
  });

  it("after saving, comes back to an answer skipped earlier", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("button", { name: /próxima/i }));
    await screen.findByText("Quanto custa o almoço?");

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
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
      items: queue().items.map((i) => (i.id === 11 ? { ...i, note: note(1, 2) } : i)),
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
      items: queue().items.map((i) => ({ ...i, note: note(2, i.grounding_applicable ? 2 : null) })),
      done: 2,
    }));
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));
    await userEvent.click(await screen.findByRole("button", { name: /piloto/i }));

    await waitFor(() => expect(screen.getByText(/2 de 2 avaliadas/i)).toBeInTheDocument());
  });

  it("shows Fundamentação as not applicable when nothing was retrieved, and saves it as null", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("button", { name: /próxima/i }));
    await screen.findByText("Quanto custa o almoço?");

    expect(screen.getByText(/não se aplica/i)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Fundamentação/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
    await userEvent.click(screen.getByRole("button", { name: /salvar e seguir/i }));

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(12, 3, note(2, null));
  });

  it("lets the Avaliador say they cannot evaluate, with a reason", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("checkbox", { name: /não consigo avaliar/i }));
    expect(screen.getByRole("button", { name: /salvar e seguir/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/por quê/i), "Referência ambígua");
    await userEvent.click(screen.getByRole("button", { name: /salvar e seguir/i }));

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(11, 3, {
      correctness: null, grounding: null, cannot_evaluate: true, reason: "Referência ambígua", comment: null,
    });
  });

  it("saves an optional comment with the note", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 1 · Parcial/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Fundamentação: 2 · Apoiada/ }));
    await userEvent.type(screen.getByLabelText(/comentário/i), "Faltou o nome da roda");
    await userEvent.click(screen.getByRole("button", { name: /salvar e seguir/i }));

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(11, 3, { ...note(1, 2), comment: "Faltou o nome da roda" });
  });

  it("keeps an unsaved choice when moving between answers", async () => {
    await openRound();

    await userEvent.click(screen.getByRole("radio", { name: /Correção: 1 · Parcial/ }));
    await userEvent.click(screen.getByRole("button", { name: /próxima/i }));
    await userEvent.click(await screen.findByRole("button", { name: /anterior/i }));

    expect(screen.getByRole("radio", { name: /Correção: 1 · Parcial/ })).toBeChecked();
    expect(screen.getByText(/não salva/i)).toBeInTheDocument();
  });

  it("scores and saves with the keyboard", async () => {
    await openRound();

    await userEvent.keyboard("2");
    await userEvent.keyboard("1");
    await userEvent.keyboard("{Enter}");

    expect(client.saveAnnotationNote).toHaveBeenCalledWith(11, 3, note(2, 1));
    expect(await screen.findByText("Quanto custa o almoço?")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowLeft}");
    expect(await screen.findByText("Quantos metros tem a roda-gigante?")).toBeInTheDocument();
  });

  it("shows the keyboard shortcuts", async () => {
    await openRound();

    expect(screen.getByText(/atalhos/i)).toBeInTheDocument();
  });

  it("does not flag as unsaved a comment typed and erased", async () => {
    await openRound();

    await userEvent.type(screen.getByLabelText(/comentário/i), "x");
    await userEvent.clear(screen.getByLabelText(/comentário/i));

    expect(screen.queryByText(/não salva/i)).not.toBeInTheDocument();
  });

  it("leaves Enter on a focused button to the button", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Fundamentação: 2 · Apoiada/ }));

    screen.getByRole("button", { name: /próxima/i }).focus();
    await userEvent.keyboard("{Enter}");

    expect(client.saveAnnotationNote).not.toHaveBeenCalled();
    expect(await screen.findByText("Quanto custa o almoço?")).toBeInTheDocument();
  });

  describe("as adjudicator", () => {
    const view = {
      round: { ...round, id: 8, name: "principal", status: "closed" as const, adjudicator_id: 3 },
      decided: 0, total: 1,
      items: [{
        id: 40, position: 2, question: "Qual é o telefone da Defesa Civil?", reference_answer: "199.",
        evidence: ["Defesa Civil: 199"], retrieved_context: ["Defesa Civil 199, 24 horas"],
        generated_answer: "É o 199.", grounding_applicable: true,
        notes: { Bruno: note(1, 2), Caio: note(2, 2) }, disputed: ["correctness" as const], adjudication: null,
      }],
    };

    beforeEach(() => {
      vi.mocked(client.listAnnotationRounds).mockResolvedValue([round, view.round]);
      vi.mocked(client.getAdjudication).mockResolvedValue(view);
      vi.mocked(client.saveAdjudication).mockResolvedValue({ item_id: 40, correctness: 2, grounding: null });
    });

    it("offers the closed Rodadas the Avaliador adjudicates", async () => {
      renderPage();
      await userEvent.click(await screen.findByRole("button", { name: "Ana" }));

      expect(await screen.findByRole("button", { name: /adjudicar principal/i })).toBeInTheDocument();
    });

    it("shows the others' notes on the disputed answer and records the decision", async () => {
      renderPage();
      await userEvent.click(await screen.findByRole("button", { name: "Ana" }));
      await userEvent.click(await screen.findByRole("button", { name: /adjudicar principal/i }));

      expect(await screen.findByText("Qual é o telefone da Defesa Civil?")).toBeInTheDocument();
      expect(client.getAdjudication).toHaveBeenCalledWith(8, 3);
      expect(screen.getByText(/Bruno: 1 \/ 2/)).toBeInTheDocument();
      expect(screen.getByText(/Caio: 2 \/ 2/)).toBeInTheDocument();
      // only the disputed dimension is decided
      expect(screen.queryByRole("radio", { name: /Fundamentação/ })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("radio", { name: /Correção: 2 · Correta/ }));
      await userEvent.click(screen.getByRole("button", { name: /salvar decisão/i }));

      expect(client.saveAdjudication).toHaveBeenCalledWith(40, 3, { correctness: 2, grounding: null });
      expect(await screen.findByText(/1 de 1 decididas/i)).toBeInTheDocument();
    });
  });

  it("offers a retest Rodada only to its Avaliador", async () => {
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([
      { ...round, id: 7, name: "piloto · reteste de Ana", retest_annotator_id: 3 },
      { ...round, id: 9, name: "principal · reteste de Bruno", retest_annotator_id: 4 },
    ]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Ana" }));

    expect(await screen.findByRole("button", { name: /reteste de Ana/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reteste de Bruno/i })).not.toBeInTheDocument();
  });

  it("explains how to evaluate in a popup available at every step", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /como avaliar/i }));

    const dialog = await screen.findByRole("dialog", { name: /como avaliar/i });
    expect(within(dialog).getByText(/0 · errada/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/compare com os trechos recuperados/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/não se aplica/i).length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText(/não consigo avaliar/i).length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/atalhos/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: /entendi/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps the help available while evaluating", async () => {
    await openRound();

    expect(screen.getByRole("button", { name: /como avaliar/i })).toBeInTheDocument();
  });

  it("does not score with the keyboard while the help is open", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("button", { name: /como avaliar/i }));
    await screen.findByRole("dialog");

    // From a non-button element, so only the "help is open" guard can stop the shortcut.
    fireEvent.keyDown(document.body, { key: "2" });

    expect(screen.getByRole("radio", { name: /Correção: 2 · Correta/, hidden: true })).not.toBeChecked();
  });

  it("gives the shortcuts back to the screen when the help closes", async () => {
    await openRound();
    await userEvent.click(screen.getByRole("button", { name: /como avaliar/i }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /entendi/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await userEvent.keyboard("2");

    expect(screen.getByRole("radio", { name: /Correção: 2 · Correta/ })).toBeChecked();
  });
});

