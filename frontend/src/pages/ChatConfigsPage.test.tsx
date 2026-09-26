import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ChatConfigsPage } from "./ChatConfigsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/chat-configs"]}>
      <MantineProvider>
        <ChatConfigsPage />
      </MantineProvider>
    </MemoryRouter>,
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

  it("includes rag in the created config", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome/i), "c-rag");
    await user.click(screen.getByRole("button", { name: /criar/i }));
    await waitFor(() =>
      expect(client.createChatConfig).toHaveBeenCalledWith(
        expect.objectContaining({ rag: expect.any(String) }),
      ),
    );
  });

  it("preselects a local model over Gemini", async () => {
    vi.mocked(client.getOptions).mockResolvedValue({
      bases: ["viagem"], chunkings: ["recursive"], embeddings: ["e5"], rags: ["naive"],
      retrievers: ["similarity"], metrics: ["rouge_l"],
      llms: ["gemini-2.5-flash-lite", "qwen3:1.7b"],
      llm_options: [
        { value: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite", location: "remote" },
        { value: "qwen3:1.7b", label: "qwen3:1.7b", location: "local" },
      ],
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome/i), "c-local");
    await user.click(screen.getByRole("button", { name: /criar/i }));
    await waitFor(() =>
      expect(client.createChatConfig).toHaveBeenCalledWith(expect.objectContaining({ llm: "qwen3:1.7b" })),
    );
  });
});
