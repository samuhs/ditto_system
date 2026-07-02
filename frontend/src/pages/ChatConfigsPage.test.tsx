import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ChatConfigsPage } from "./ChatConfigsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ChatConfigsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["viagem"], chunkings: ["recursive"], embeddings: ["gemini"], llms: ["gemini"],
    rags: ["naive"], retrievers: ["similarity"], metrics: ["rouge_l"],
  });
  vi.mocked(client.getPersonas).mockResolvedValue({ personas: ["travel_guide", "assistant"] });
  vi.mocked(client.listChatConfigs).mockResolvedValue([]);
  vi.mocked(client.createChatConfig).mockResolvedValue({ id: 1, name: "c1" });
});

describe("ChatConfigsPage", () => {
  it("loads options and personas", async () => {
    renderPage();
    expect(await screen.findByLabelText(/nome/i)).toBeInTheDocument();
  });

  it("creates a chat config", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome/i), "c1");
    await user.click(screen.getByRole("button", { name: /criar/i }));
    await waitFor(() => expect(client.createChatConfig).toHaveBeenCalled());
  });
});
