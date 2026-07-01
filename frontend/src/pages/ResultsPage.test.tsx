import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
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
  vi.mocked(client.listExperiments).mockResolvedValue([
    { id: 7, name: "kind-ember-89", status: "done" },
    { id: 8, name: "swift-fox-12", status: "pending" },
  ]);
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
});
