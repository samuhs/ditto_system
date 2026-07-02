import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ChatPage } from "./ChatPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ChatPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listChatConfigs).mockResolvedValue([
    { id: 1, name: "c1", base: "viagem", chunking: "recursive", embedding: "gemini", retriever: "similarity", rag: "naive", llm: "gemini", persona: "travel_guide" },
  ]);
  vi.mocked(client.sendChat).mockResolvedValue({ reply: "Olá! Sou seu guia.", contexts: [] });
  vi.mocked(client.saveDialogue).mockResolvedValue({ id: 5 });
});

describe("ChatPage", () => {
  it("sends a message and shows the reply", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/c1/); // config option loaded
    await user.type(screen.getByPlaceholderText(/mensagem/i), "Oi");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(client.sendChat).toHaveBeenCalledWith(1, [{ role: "user", content: "Oi" }]));
    expect(await screen.findByText(/Sou seu guia/)).toBeInTheDocument();
  });

  it("saves the dialogue", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/c1/);
    await user.type(screen.getByPlaceholderText(/mensagem/i), "Oi");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await screen.findByText(/Sou seu guia/);
    await user.click(screen.getByRole("button", { name: /salvar di/i }));
    await waitFor(() => expect(client.saveDialogue).toHaveBeenCalledWith(1, [
      { role: "user", content: "Oi" },
      { role: "assistant", content: "Olá! Sou seu guia." },
    ]));
  });
});
