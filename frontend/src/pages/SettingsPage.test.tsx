import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor, within } from "@testing-library/react";
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

function section(heading: string) {
  return screen.getByText(heading).closest("section") as HTMLElement;
}

beforeEach(() => {
  vi.mocked(client.getSettings).mockResolvedValue({
    gemini_api_key_set: false,
    stall_limit_minutes: 10,
  });
  vi.mocked(client.saveGeminiKey).mockResolvedValue({ gemini_api_key_set: true });
  vi.mocked(client.saveStallLimit).mockResolvedValue({ stall_limit_minutes: 5 });
  vi.mocked(client.getMemory).mockResolvedValue({
    profile: { name: "low", max_local_models: 1, embedding_device: "cpu", max_concurrency: 2 },
    total_bytes: 8 * 1024 ** 3,
    available_bytes: 2 * 1024 ** 3,
    process_memory_bytes: 1024 ** 3,
    loaded_models: [{ name: "e5", device: "cpu", local: true, in_use: 0 }],
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
    expect(await screen.findByText(/Nenhuma chave configurada/)).toBeInTheDocument();
  });

  it("loads settings and shows the key state", async () => {
    renderPage();
    expect(await screen.findByText(/Nenhuma chave configurada/)).toBeInTheDocument();
  });

  it("saves the gemini key", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/Nenhuma chave configurada/);
    const geminiSection = section("Chave do Gemini");
    await user.type(within(geminiSection).getByLabelText(/Nova chave/), "abc");
    await user.click(within(geminiSection).getByRole("button", { name: /^salvar$/i }));
    await waitFor(() => expect(client.saveGeminiKey).toHaveBeenCalledWith("abc"));
  });

  it("shows the Travamento limit and saves a new one", async () => {
    renderPage();
    await screen.findByText(/Nenhuma chave configurada/);
    const stallSection = section("Travamento");
    expect(within(stallSection).getByLabelText(/Pausar experimento travado após \(min\)/)).toHaveValue(
      "10",
    );

    const user = userEvent.setup();
    const input = within(stallSection).getByLabelText(/Pausar experimento travado após \(min\)/);
    await user.clear(input);
    await user.type(input, "5");
    await user.click(within(stallSection).getByRole("button", { name: /^salvar$/i }));
    await waitFor(() => expect(client.saveStallLimit).toHaveBeenCalledWith(5));
    expect(await within(stallSection).findByText("Limite salvo")).toBeInTheDocument();
  });
});
