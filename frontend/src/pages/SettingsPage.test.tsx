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
  vi.mocked(client.saveOllamaModels).mockResolvedValue({
    ollama_models: [{ id: "qwen", model: "qwen2.5:3b-instruct" }],
  });
});

describe("SettingsPage", () => {
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
