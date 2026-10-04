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

beforeEach(() => {
  vi.mocked(client.listBases).mockResolvedValue([VIAGEM]);
  vi.mocked(client.deleteBase).mockResolvedValue({ base: "viagem", deleted: [] });
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
