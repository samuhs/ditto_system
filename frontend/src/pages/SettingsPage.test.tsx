import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <SettingsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getSettings).mockResolvedValue({
    gemini_api_key_set: false,
    ollama_models: [{ id: "qwen", model: "qwen2.5:3b-instruct" }],
  });
  vi.mocked(client.saveGeminiKey).mockResolvedValue({ gemini_api_key_set: true });
  vi.mocked(client.getMemory).mockResolvedValue({
    profile: { name: "low", max_local_models: 1, embedding_device: "cpu", max_concurrency: 2 },
    total_bytes: 8 * 1024 ** 3,
    available_bytes: 2 * 1024 ** 3,
    process_memory_bytes: 1024 ** 3,
    loaded_models: [{ name: "e5", device: "cpu", local: true, in_use: 0 }],
  });
  vi.mocked(client.saveOllamaModels).mockResolvedValue({
    ollama_models: [{ id: "qwen", model: "qwen2.5:3b-instruct" }],
  });
});

describe("SettingsPage", () => {
  it("shows the memory profile and how to switch it", async () => {
    renderPage();
    expect(await screen.findByText("Perfil low")).toBeInTheDocument();
    expect(screen.getByText("make memory-profile PROFILE=standard")).toBeInTheDocument();
    expect(screen.getByText(/e5 \(cpu\)/)).toBeInTheDocument();
  });

  it("keeps the page working when memory status fails", async () => {
    vi.mocked(client.getMemory).mockRejectedValue(new Error("down"));
    renderPage();
    expect(await screen.findByText(/Não foi possível ler o estado da memória/)).toBeInTheDocument();
    expect(await screen.findByDisplayValue("qwen")).toBeInTheDocument();
  });

  it("loads settings and shows key state + models", async () => {
    renderPage();
    expect(await screen.findByText(/Nenhuma chave configurada/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("qwen")).toBeInTheDocument();
  });

  it("saves the gemini key", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/Nenhuma chave configurada/);
    await user.type(screen.getByLabelText(/Nova chave/), "abc");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));
    await waitFor(() => expect(client.saveGeminiKey).toHaveBeenCalledWith("abc"));
  });

  it("saves the ollama models", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByDisplayValue("qwen");
    await user.click(screen.getByRole("button", { name: /salvar modelos/i }));
    await waitFor(() =>
      expect(client.saveOllamaModels).toHaveBeenCalledWith([
        { id: "qwen", model: "qwen2.5:3b-instruct" },
      ]),
    );
  });
});
