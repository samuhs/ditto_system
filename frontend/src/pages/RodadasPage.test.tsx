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
  experiment_ids: [90], size: 10, created_at: "2026-10-13T03:00:00",
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

  it("creates a Rodada from an Experimento with the sample size and the seed", async () => {
    vi.mocked(client.createAnnotationRound).mockResolvedValue({ ...round, id: 6, name: "principal" });
    renderAt("/anotacao");

    await userEvent.type(await screen.findByLabelText(/nome da rodada/i), "principal");
    await userEvent.click(screen.getByRole("textbox", { name: /experimento/i }));
    await userEvent.click(await screen.findByRole("option", { name: /#90 · B2.E3.1-qwen35-4b/ }));
    await userEvent.clear(screen.getByLabelText(/respostas a sortear/i));
    await userEvent.type(screen.getByLabelText(/respostas a sortear/i), "20");
    await userEvent.type(screen.getByLabelText(/semente/i), "11");
    await userEvent.click(screen.getByRole("button", { name: /criar rodada/i }));

    expect(client.createAnnotationRound).toHaveBeenCalledWith({
      name: "principal", experiment_id: 90, sample_size: 20, seed: 11,
    });
  });

  it("lists the Rodadas with size, status and a link to each one", async () => {
    renderAt("/anotacao");

    const link = await screen.findByRole("link", { name: /piloto/i });
    expect(link).toHaveAttribute("href", "/anotacao/5");
    expect(screen.getByText(/10 respostas/)).toBeInTheDocument();
    expect(screen.getByText(/aberta/i)).toBeInTheDocument();
  });

  it("points the Avaliadores to the evaluation screen", async () => {
    renderAt("/anotacao");

    expect(await screen.findByRole("link", { name: /abrir a tela de avaliação/i })).toHaveAttribute("href", "/anotar");
  });
});

describe("RodadaDetailPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
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

  it("says when nobody has evaluated yet", async () => {
    vi.mocked(client.getAnnotationRound).mockResolvedValue({ ...round, progress: [] });
    renderAt("/anotacao/5");

    expect(await screen.findByText(/ninguém avaliou/i)).toBeInTheDocument();
  });
});
