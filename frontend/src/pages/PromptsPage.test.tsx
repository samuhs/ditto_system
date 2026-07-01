import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { PromptsPage } from "./PromptsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <PromptsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getPrompts).mockResolvedValue({
    naive: { answer: { text: "Use {context} and {question}.", required_placeholders: ["context", "question"] } },
  });
  vi.mocked(client.savePrompt).mockResolvedValue({ technique: "naive", key: "answer", text: "x" });
});

describe("PromptsPage", () => {
  it("loads and shows the prompt text and its required placeholders", async () => {
    renderPage();
    expect(await screen.findByDisplayValue(/Use \{context\} and \{question\}/)).toBeInTheDocument();
    expect(screen.getAllByText(/context/).length).toBeGreaterThan(0);
  });

  it("saves an edited prompt", async () => {
    renderPage();
    const user = userEvent.setup();
    const area = await screen.findByDisplayValue(/Use \{context\}/);
    await user.clear(area);
    await user.type(area, "New {{context} {{question}");
    await user.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() =>
      expect(client.savePrompt).toHaveBeenCalledWith("naive", "answer", "New {context} {question}"),
    );
  });
});
