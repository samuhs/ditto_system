import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

import * as client from "./api/client";

vi.mock("./api/client");

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: [], chunkings: [], embeddings: [], llms: [], rags: [], retrievers: [], metrics: [],
  });
  vi.mocked(client.listExperiments).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
});

function renderApp() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("App shell", () => {
  it("renders the home hero and primary navigation", async () => {
    renderApp();
    expect(await screen.findByText(/Vire especialista/i)).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: /navegação principal/i });
    // one tab per task stage, in workflow order
    expect(within(nav).getByRole("link", { name: /preparar/i })).toHaveAttribute("href", "/ingest");
    expect(within(nav).getByRole("link", { name: /experimentar/i })).toHaveAttribute("href", "/experiment");
    expect(within(nav).getByRole("link", { name: /comparar/i })).toHaveAttribute("href", "/results");
    expect(within(nav).getByRole("link", { name: /conversar/i })).toHaveAttribute("href", "/chat");
  });

  it("points a first-time user to their documents", async () => {
    renderApp();
    expect(await screen.findByRole("link", { name: /preparar documentos/i })).toHaveAttribute("href", "/ingest");
  });
});
