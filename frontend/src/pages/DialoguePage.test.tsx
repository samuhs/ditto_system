import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DialoguePage } from "./DialoguePage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/dialogues/5"]}>
        <Routes>
          <Route path="/dialogues/:id" element={<DialoguePage />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getDialogue).mockResolvedValue({
    id: 5,
    created_at: "2026-07-02T10:00:00",
    rating: null,
    config_snapshot: { name: "c1", persona: "travel_guide", base: "viagem", rag: "naive", llm: "gemini" },
    messages: [
      { role: "user", content: "Quais praias?" },
      { role: "assistant", content: "Praia X e Y." },
    ],
  });
  vi.mocked(client.saveDialogueRating).mockResolvedValue({ id: 5, rating: 8 });
});

describe("DialoguePage", () => {
  it("shows the conversation and config summary", async () => {
    renderPage();
    expect(await screen.findByText("Quais praias?")).toBeInTheDocument();
    expect(screen.getByText("Praia X e Y.")).toBeInTheDocument();
    expect(screen.getByText("travel_guide")).toBeInTheDocument();
  });

  it("saves a rating", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Quais praias?");
    await user.type(screen.getByLabelText("Nota (0–10)"), "8");
    await user.click(screen.getByRole("button", { name: /salvar nota/i }));
    await waitFor(() => expect(client.saveDialogueRating).toHaveBeenCalledWith(5, 8));
    expect(await screen.findByText("Nota salva")).toBeInTheDocument();
  });
});
