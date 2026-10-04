import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { BaseSummary } from "../api/types";
import { BasesPage } from "./BasesPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <BasesPage />
      </MemoryRouter>
    </MantineProvider>,
  );
}

const VIAGEM: BaseSummary = {
  name: "viagem",
  in_use: null,
  indexes: [
    { chunking: "fixed", embedding: "e5", chunks: 12, graphs: [] },
    {
      chunking: "recursive",
      embedding: "gemini",
      chunks: 40,
      graphs: [
        {
          extractor: "qwen3:1.7b",
          entities: 120,
          relations: 85,
          failed_pct: 3.5,
          built_at: "2026-10-01T12:00:00+00:00",
        },
      ],
    },
  ],
};

function job(overrides: Partial<import("../api/types").GraphBuildJob> = {}): import("../api/types").GraphBuildJob {
  return {
    id: 9,
    base: "viagem",
    extractor: "qwen3:1.7b",
    status: "pending",
    pause_requested: false,
    created_at: "2026-10-04T10:00:00Z",
    finished_at: null,
    indexes: [
      { chunking: "fixed", embedding: "e5", status: "pending", extracted: 0, total: 12, stats: null, error: null },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(client.listBases).mockResolvedValue([VIAGEM]);
  vi.mocked(client.deleteBase).mockResolvedValue({ base: "viagem", deleted: [] });
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["viagem"],
    chunkings: ["fixed", "recursive"],
    embeddings: ["e5", "gemini"],
    llm_options: [
      { value: "qwen3:1.7b", label: "qwen3:1.7b", location: "local" },
      { value: "gemini", label: "gemini", location: "remote" },
    ],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["rouge_l"],
  });
  vi.mocked(client.startGraphBuild).mockResolvedValue(job());
  vi.mocked(client.pauseGraphBuild).mockResolvedValue(job({ status: "paused", pause_requested: true }));
  vi.mocked(client.resumeGraphBuild).mockResolvedValue(job({ status: "pending" }));
});

describe("BasesPage", () => {
  it("lists each Base with its Índices and their Grafos de conhecimento", async () => {
    renderPage();
    const base = await screen.findByRole("region", { name: "viagem" });
    const indexes = within(base).getByRole("table", { name: /índices/i });
    const rows = within(indexes).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByText("Recursivo")).toBeInTheDocument();
    expect(within(rows[1]).getByText("40")).toBeInTheDocument();

    const graphs = within(base).getByRole("table", { name: /grafos de conhecimento/i });
    const graph = within(graphs).getAllByRole("row")[1];
    expect(within(graph).getByText("qwen3:1.7b")).toBeInTheDocument();
    expect(within(graph).getByText("120")).toBeInTheDocument();
    expect(within(graph).getByText("85")).toBeInTheDocument();
    expect(within(graph).getByText("3,5%")).toBeInTheDocument();
    expect(within(graph).getByText("01/10/2026")).toBeInTheDocument();
  });

  it("shows a Grafo build in progress with its chunks extracted", async () => {
    vi.mocked(client.listBases).mockResolvedValue([{
      ...VIAGEM,
      in_use: "Um Grafo de conhecimento da base \"viagem\" está sendo construído.",
      graph_builds: [{
        id: 3, base: "viagem", extractor: "qwen3:1.7b", status: "running", pause_requested: false,
        created_at: "2026-10-04T10:00:00Z", finished_at: null,
        indexes: [{ chunking: "fixed", embedding: "e5", status: "building", extracted: 5, total: 12,
                    stats: null, error: null }],
      }],
    }]);
    renderPage();
    expect(await screen.findByText("Construindo Grafo: 5 / 12 trechos")).toBeInTheDocument();
  });

  it("says where a missing Grafo comes from", async () => {
    vi.mocked(client.listBases).mockResolvedValue([{
      ...VIAGEM, indexes: [{ chunking: "fixed", embedding: "e5", chunks: 12, graphs: [] }],
    }]);
    renderPage();
    expect(await screen.findByText(/clique em.*gerar grafo/i)).toBeInTheDocument();
  });

  it("opens the Gerar Grafo form with every Índice picked by default and starts a build", async () => {
    renderPage();
    const user = userEvent.setup();
    const base = await screen.findByRole("region", { name: "viagem" });
    await user.click(within(base).getByRole("button", { name: /gerar grafo/i }));

    const dialog = await screen.findByRole("dialog");
    within(dialog).getAllByRole("checkbox").forEach((checkbox) => expect(checkbox).toBeChecked());
    expect(client.getOptions).toHaveBeenCalled();

    await user.click(within(dialog).getByRole("textbox", { name: /llm extrator/i }));
    await user.click(await screen.findByRole("option", { name: /qwen3:1\.7b/i }));
    await user.click(within(dialog).getByRole("button", { name: /construir grafo/i }));

    await waitFor(() => expect(client.startGraphBuild).toHaveBeenCalledWith({
      base: "viagem",
      extractor: "qwen3:1.7b",
      indexes: [
        { chunking: "fixed", embedding: "e5" },
        { chunking: "recursive", embedding: "gemini" },
      ],
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("lets the user pick fewer Índices before building", async () => {
    renderPage();
    const user = userEvent.setup();
    const base = await screen.findByRole("region", { name: "viagem" });
    await user.click(within(base).getByRole("button", { name: /gerar grafo/i }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getAllByRole("checkbox")[1]);
    await user.click(within(dialog).getByRole("textbox", { name: /llm extrator/i }));
    await user.click(await screen.findByRole("option", { name: /qwen3:1\.7b/i }));
    await user.click(within(dialog).getByRole("button", { name: /construir grafo/i }));

    await waitFor(() => expect(client.startGraphBuild).toHaveBeenCalledWith({
      base: "viagem",
      extractor: "qwen3:1.7b",
      indexes: [{ chunking: "fixed", embedding: "e5" }],
    }));
  });

  it("shows a build it just started, with pause and resume", async () => {
    vi.mocked(client.listBases)
      .mockResolvedValueOnce([VIAGEM])
      .mockResolvedValue([{
        ...VIAGEM,
        in_use: 'Um Grafo de conhecimento da base "viagem" está sendo construído (LLM extrator qwen3:1.7b).',
        graph_builds: [job({
          status: "running",
          indexes: [{ chunking: "fixed", embedding: "e5", status: "building", extracted: 5, total: 12, stats: null, error: null }],
        })],
      }]);
    renderPage();
    const user = userEvent.setup();
    const base = await screen.findByRole("region", { name: "viagem" });
    await user.click(within(base).getByRole("button", { name: /gerar grafo/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("textbox", { name: /llm extrator/i }));
    await user.click(await screen.findByRole("option", { name: /qwen3:1\.7b/i }));
    await user.click(within(dialog).getByRole("button", { name: /construir grafo/i }));

    expect(await screen.findByText("Construindo Grafo: 5 / 12 trechos")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /pausar/i }));
    expect(client.pauseGraphBuild).toHaveBeenCalledWith(9);
  });

  it("disables Gerar Grafo while the Base is in use", async () => {
    vi.mocked(client.listBases).mockResolvedValue([{
      ...VIAGEM, in_use: 'O experimento "exp-1" está na fila.',
    }]);
    renderPage();
    const base = await screen.findByRole("region", { name: "viagem" });
    expect(within(base).getByRole("button", { name: /gerar grafo/i })).toBeDisabled();
  });

  it("teaches the next step when there is no Base yet", async () => {
    vi.mocked(client.listBases).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByRole("link", { name: /enviar documentos/i })).toHaveAttribute("href", "/ingest");
  });

  it("deletes a Base after confirming in a dialog", async () => {
    vi.mocked(client.listBases).mockResolvedValueOnce([VIAGEM]).mockResolvedValueOnce([]);
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /apagar base/i }));

    const dialog = await screen.findByRole("dialog");
    expect(client.deleteBase).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: /apagar base/i }));

    await waitFor(() => expect(client.deleteBase).toHaveBeenCalledWith("viagem"));
    expect(await screen.findByText(/base “viagem” apagada/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("region", { name: "viagem" })).not.toBeInTheDocument());
  });

  it("keeps the Base and shows why when the deletion is refused", async () => {
    const reason = 'O experimento "exp-1" está rodando sobre a base "viagem".';
    vi.mocked(client.deleteBase).mockRejectedValue(new Error(reason));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /apagar base/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /apagar base/i }));

    expect(await within(dialog).findByText(reason)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "viagem" })).toBeInTheDocument();
    // The list is read again, so its "Em uso agora" note catches up.
    await waitFor(() => expect(client.listBases).toHaveBeenCalledTimes(2));
  });

  it("cancels without deleting", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /apagar base/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /cancelar/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(client.deleteBase).not.toHaveBeenCalled();
  });

  it("says when a Base is in use", async () => {
    vi.mocked(client.listBases).mockResolvedValue([{ ...VIAGEM, in_use: "O experimento \"exp-1\" está na fila." }]);
    renderPage();
    expect(await screen.findByText(/está na fila/)).toBeInTheDocument();
  });
});
