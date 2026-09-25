import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { AvaliacaoPage } from "./AvaliacaoPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <AvaliacaoPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getEvaluationSettings).mockResolvedValue({
    eval_embedding: "paraphrase",
    embeddings: [
      { name: "gemini", local: false },
      { name: "paraphrase", local: true },
    ],
    metrics: [
      { name: "answer_relevancy", uses_embedding: true, requires_reference: false },
      { name: "rouge_l", uses_embedding: false, requires_reference: true },
    ],
  });
  vi.mocked(client.saveEvalEmbedding).mockResolvedValue({ eval_embedding: "gemini" });
});

describe("AvaliacaoPage", () => {
  it("marks the saved embedder and tells local from API ones", async () => {
    renderPage();
    expect(await screen.findByRole("radio", { name: /Paraphrase/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Gemini/ })).not.toBeChecked();
    expect(screen.getByText(/Cada resposta avaliada gasta cota/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar escolha" })).toBeDisabled();
  });

  it("shows which metrics depend on the embedder", async () => {
    renderPage();
    expect(await screen.findByText("O modelo escolhido")).toBeInTheDocument();
    expect(screen.getByText("Só o texto")).toBeInTheDocument();
  });

  it("saves a new choice", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: /Gemini/ }));
    await user.click(screen.getByRole("button", { name: "Salvar escolha" }));
    expect(client.saveEvalEmbedding).toHaveBeenCalledWith("gemini");
    expect(await screen.findByText(/Os próximos experimentos usam Gemini/)).toBeInTheDocument();
  });

  it("explains a load failure", async () => {
    vi.mocked(client.getEvaluationSettings).mockRejectedValue(new Error("down"));
    renderPage();
    expect(await screen.findByText(/Não foi possível ler a configuração de avaliação/)).toBeInTheDocument();
  });
});
