import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ResultsPage } from "./ResultsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/results"]}>
        <Routes>
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/results/:id" element={<div>DETALHE {"placeholder"}</div>} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listExperiments).mockResolvedValue({
    items: [
      { id: 7, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" },
      { id: 8, name: "swift-fox-12", status: "pending", created_at: "2026-07-04T09:00:00" },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  });
});

describe("ResultsPage", () => {
  it("shows the experiment list on load", async () => {
    renderPage();
    expect(await screen.findByText("kind-ember-89")).toBeInTheDocument();
    expect(screen.getByText("swift-fox-12")).toBeInTheDocument();
  });

  it("navigates to the experiment page when an experiment is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByText("kind-ember-89"));
    expect(await screen.findByText(/DETALHE/)).toBeInTheDocument();
  });

  it("shows the start date of each experiment", async () => {
    renderPage();
    await screen.findByText("kind-ember-89");
    expect(screen.getAllByText(/2026/).length).toBeGreaterThan(0);
  });

  it("paginates via the page control", async () => {
    vi.mocked(client.listExperiments).mockResolvedValue({
      items: [{ id: 7, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" }],
      total: 40,
      page: 1,
      page_size: 20,
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("kind-ember-89");
    await user.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(client.listExperiments).toHaveBeenCalledWith(2, 20));
  });
});
