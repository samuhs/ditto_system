import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { RodadaDetailPage, RodadasPage } from "./RodadasPage";

vi.mock("../api/client");

const round = {
  id: 5, name: "piloto", description: "", status: "open" as const, seed: 7, rubric_version: 1,
  experiment_ids: [90], size: 10, pilot: false, strata: [], allocation: "proportional" as const,
  created_at: "2026-10-13T03:00:00",
};

function renderAt(url: string) {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/anotacao" element={<RodadasPage />} />
          <Route path="/anotacao/:id" element={<RodadaDetailPage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("RodadasPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.listAnnotators).mockResolvedValue([
      { id: 3, name: "Ana", active: true }, { id: 4, name: "Bruno", active: false },
    ]);
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([round]);
    vi.mocked(client.listExperiments).mockResolvedValue({
      items: [{ id: 90, name: "B2.E3.1-qwen35-4b", status: "done", base: "campanha-b2", created_at: "" }],
      total: 1, page: 1, page_size: 100,
    });
    vi.mocked(client.listBases).mockResolvedValue([{ name: "campanha-b2", indexes: [] }] as never);
    vi.mocked(client.getExperiment).mockResolvedValue({
      runs: [{ id: 7, chunking: "markdown", embedding: "e5", rag: "agentic", retriever: "similarity",
        llm: "Qwen3.5-4B" }],
    } as never);
  });

  it("lists the Avaliadores and lets the researcher deactivate an active one", async () => {
    vi.mocked(client.setAnnotatorActive).mockResolvedValue({ id: 3, name: "Ana", active: false });
    renderAt("/anotacao");

    const row = (await screen.findByText("Ana")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: /desativar/i }));

    expect(client.setAnnotatorActive).toHaveBeenCalledWith(3, false);
    const bruno = screen.getByText("Bruno").closest("tr")!;
    expect(within(bruno).getByRole("button", { name: /reativar/i })).toBeInTheDocument();
  });

  async function pickCombination() {
    await userEvent.selectOptions(await screen.findByLabelText("Base"), "campanha-b2");
    await userEvent.selectOptions(await screen.findByLabelText("Experimento"), "90");
    const picker = screen.getByRole("region", { name: /adicionar combinações/i });
    await userEvent.click(await within(picker).findByRole("checkbox"));
  }

  it("creates a stratified Rodada from the chosen Combinações", async () => {
    vi.mocked(client.createAnnotationRound).mockResolvedValue({ ...round, id: 6, name: "principal" });
    renderAt("/anotacao");

    await userEvent.type(await screen.findByLabelText(/nome da rodada/i), "principal");
    await pickCombination();
    await userEvent.clear(screen.getByLabelText(/respostas a sortear/i));
    await userEvent.type(screen.getByLabelText(/respostas a sortear/i), "20");
    await userEvent.type(screen.getByLabelText(/semente/i), "11");
    await userEvent.click(screen.getByRole("checkbox", { name: /tipo de pergunta/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /técnica rag/i }));
    await userEvent.click(screen.getByRole("radio", { name: /igual por estrato/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /rodada piloto/i }));
    await userEvent.click(screen.getByRole("button", { name: /criar rodada/i }));

    expect(client.createAnnotationRound).toHaveBeenCalledWith({
      name: "principal", items: ["90:7"], sample_size: 20, seed: 11,
      strata: ["question_type", "rag"], allocation: "equal", pilot: true,
    });
  });

  it("previews how many answers each stratum gives and warns about short ones", async () => {
    vi.mocked(client.previewAnnotationRound).mockResolvedValue({
      available: 21, size: 6,
      strata: [
        { key: { question_type: "ponte" }, available: 1, allocated: 1, short: true },
        { key: { question_type: "simples" }, available: 20, allocated: 5, short: false },
      ],
    });
    renderAt("/anotacao");
    await userEvent.type(await screen.findByLabelText(/nome da rodada/i), "x");
    await pickCombination();
    await userEvent.click(screen.getByRole("checkbox", { name: /tipo de pergunta/i }));

    await userEvent.click(screen.getByRole("button", { name: /ver prévia/i }));

    const ponte = (await screen.findByText("ponte")).closest("tr")!;
    expect(within(ponte).getByText("1 de 1")).toBeInTheDocument();
    expect(within(ponte).getByText(/faltam respostas/i)).toBeInTheDocument();
    const simples = screen.getByText("simples").closest("tr")!;
    expect(within(simples).getByText("5 de 20")).toBeInTheDocument();
  });

  it("lists the Rodadas with size, status and a link to each one", async () => {
    renderAt("/anotacao");

    const link = await screen.findByRole("link", { name: /piloto/i });
    expect(link).toHaveAttribute("href", "/anotacao/5");
    expect(screen.getByText(/10 respostas/)).toBeInTheDocument();
    expect(screen.getByText(/aberta/i)).toBeInTheDocument();
  });

  it("marks pilot Rodadas", async () => {
    vi.mocked(client.listAnnotationRounds).mockResolvedValue([{ ...round, pilot: true }]);
    renderAt("/anotacao");

    const row = (await screen.findByRole("link", { name: /piloto/i })).closest("tr")!;
    expect(within(row).getByText(/fora da análise/i)).toBeInTheDocument();
  });

  it("points the Avaliadores to the evaluation screen", async () => {
    renderAt("/anotacao");

    expect(await screen.findByRole("link", { name: /abrir a tela de avaliação/i })).toHaveAttribute("href", "/anotar");
  });
});

describe("RodadaDetailPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getAnnotationAgreement).mockResolvedValue({
      round, avaliadores: [], note: "sem dados", disagreements: [],
      dimensions: {
        correctness: { n: 0, alpha: { value: null, low: null, high: null }, kappa: null, confusion: null },
        grounding: { n: 0, alpha: { value: null, low: null, high: null }, kappa: null, confusion: null },
      },
    });
    vi.mocked(client.getAnnotationRound).mockResolvedValue({
      ...round,
      progress: [
        { annotator_id: 3, name: "Ana", done: 7, total: 10 },
        { annotator_id: 4, name: "Bruno", done: 10, total: 10 },
      ],
    });
  });

  it("shows the progress of each Avaliador", async () => {
    renderAt("/anotacao/5");

    const ana = (await screen.findByText("Ana")).closest("tr")!;
    expect(within(ana).getByText("7 de 10")).toBeInTheDocument();
    const bruno = screen.getByText("Bruno").closest("tr")!;
    expect(within(bruno).getByText("10 de 10")).toBeInTheDocument();
    expect(client.getAnnotationRound).toHaveBeenCalledWith(5);
    expect(screen.getByText(/semente 7/i)).toBeInTheDocument();
  });

  it("removes a participant only after confirming, with their notes", async () => {
    vi.mocked(client.removeAnnotationParticipant).mockResolvedValue({ round_id: 5, annotator_id: 3, notes_deleted: 7 });
    renderAt("/anotacao/5");
    const ana = (await screen.findByText("Ana")).closest("tr")!;

    await userEvent.click(within(ana).getByRole("button", { name: /remover/i }));
    expect(client.removeAnnotationParticipant).not.toHaveBeenCalled();
    await userEvent.click(within(ana).getByRole("button", { name: /confirmar: apagar 7 notas/i }));

    expect(client.removeAnnotationParticipant).toHaveBeenCalledWith(5, 3);
    expect(client.getAnnotationRound).toHaveBeenCalledTimes(2);
  });

  it("says when nobody has evaluated yet", async () => {
    vi.mocked(client.getAnnotationRound).mockResolvedValue({ ...round, progress: [] });
    renderAt("/anotacao/5");

    expect(await screen.findByText(/ninguém avaliou/i)).toBeInTheDocument();
  });

  const agreement = {
    round, avaliadores: ["Ana", "Bruno"], note: null,
    dimensions: {
      correctness: {
        n: 10, alpha: { value: 0.812, low: 0.6, high: 0.93 }, kappa: { value: 0.7, low: 0.5, high: 0.88 },
        confusion: { avaliadores: ["Ana", "Bruno"], levels: [0, 1, 2], matrix: [[3, 1, 0], [0, 2, 1], [0, 0, 3]] },
      },
      grounding: { n: 8, alpha: { value: null, low: null, high: null }, kappa: null, confusion: null },
    },
    disagreements: [{
      item_id: 31, position: 4, question: "Qual é o telefone da Defesa Civil?", generated_answer: "199.",
      notes: {
        Ana: { correctness: 2, grounding: 2, cannot_evaluate: false, reason: null, comment: null },
        Bruno: { correctness: 1, grounding: 2, cannot_evaluate: false, reason: null, comment: "Incompleta" },
      },
    }],
  };

  function closedRound() {
    vi.mocked(client.getAnnotationRound).mockResolvedValue({
      ...round, status: "closed", progress: [{ annotator_id: 3, name: "Ana", done: 10, total: 10 }],
    });
  }

  it("computes the Concordância of an open Rodada only on demand", async () => {
    vi.mocked(client.getAnnotationAgreement).mockResolvedValue(agreement);
    renderAt("/anotacao/5");

    await userEvent.click(await screen.findByRole("button", { name: /calcular concordância/i }));

    expect(client.getAnnotationAgreement).toHaveBeenCalledWith(5);
    expect(await screen.findByText("0,81 [0,60; 0,93]")).toBeInTheDocument();
  });

  it("shows the Concordância per dimension with confidence intervals", async () => {
    closedRound();
    vi.mocked(client.getAnnotationAgreement).mockResolvedValue(agreement);
    renderAt("/anotacao/5");

    const corr = (await screen.findByText("Correção")).closest("tr")!;
    expect(within(corr).getByText("0,81 [0,60; 0,93]")).toBeInTheDocument();
    expect(within(corr).getByText("0,70 [0,50; 0,88]")).toBeInTheDocument();
    expect(within(corr).getByText("10")).toBeInTheDocument();
    const grounding = screen.getByText("Fundamentação").closest("tr")!;
    expect(within(grounding).getAllByText("—").length).toBe(2);
  });

  it("shows the confusion matrix and the disagreements to adjudicate", async () => {
    closedRound();
    vi.mocked(client.getAnnotationAgreement).mockResolvedValue(agreement);
    renderAt("/anotacao/5");

    expect(await screen.findByRole("table", { name: /matriz de confusão · correção/i })).toBeInTheDocument();
    const row = screen.getByText("Qual é o telefone da Defesa Civil?").closest("tr")!;
    expect(within(row).getByText(/Ana: 2 \/ 2/)).toBeInTheDocument();
    expect(within(row).getByText(/Bruno: 1 \/ 2/)).toBeInTheDocument();
  });

  it("closes the Rodada only after confirming", async () => {
    vi.mocked(client.closeAnnotationRound).mockResolvedValue({ ...round, status: "closed" });
    renderAt("/anotacao/5");

    await userEvent.click(await screen.findByRole("button", { name: /fechar rodada/i }));
    expect(client.closeAnnotationRound).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /confirmar: fechar/i }));

    expect(client.closeAnnotationRound).toHaveBeenCalledWith(5);
  });

  it("explains when there is no Concordância yet", async () => {
    closedRound();
    vi.mocked(client.getAnnotationAgreement).mockResolvedValue({
      ...agreement, avaliadores: ["Ana"], disagreements: [],
      note: "A Concordância precisa de pelo menos dois avaliadores nas mesmas respostas (ou de uma rodada de reteste).",
    });
    renderAt("/anotacao/5");

    expect(await screen.findByText(/precisa de pelo menos dois avaliadores/i)).toBeInTheDocument();
  });
});

