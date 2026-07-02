import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DialoguesPage } from "./DialoguesPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <DialoguesPage />
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listDialogues).mockResolvedValue({
    items: [
      { id: 1, created_at: "2026-07-02T10:00:00", rating: 8, name: "c1", persona: "travel_guide", message_count: 4, preview: "Oi" },
      { id: 2, created_at: "2026-07-01T10:00:00", rating: null, name: "c2", persona: "assistant", message_count: 2, preview: "Olá" },
    ],
    total: 2,
    page: 1,
    page_size: 20,
  });
});

describe("DialoguesPage", () => {
  it("loads with default params and lists dialogues", async () => {
    renderPage();
    expect(await screen.findByText("c1")).toBeInTheDocument();
    expect(screen.getByText("não avaliado")).toBeInTheDocument();
    expect(client.listDialogues).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20, rated: "all", sort: "recent" }),
    );
  });

  it("refetches with the rated filter and resets to page 1", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("c1");
    await user.click(screen.getAllByLabelText("Avaliação")[0]);
    await user.click(await screen.findByText("Avaliadas"));
    await waitFor(() =>
      expect(client.listDialogues).toHaveBeenCalledWith(
        expect.objectContaining({ rated: "rated", page: 1 }),
      ),
    );
  });
});
