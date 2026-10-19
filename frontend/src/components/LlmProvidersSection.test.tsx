import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { LlmProvider } from "../api/types";
import { LlmProvidersSection } from "./LlmProvidersSection";

vi.mock("../api/client");

const LOCAL: LlmProvider = {
  id: "local", kind: "custom", base_url: "http://localhost:11434/v1", api_key_env: null, api_key_set: true,
  models: [], params: {}, local: true, max_tokens_in_body: true, requests_per_minute: null, builtin: true,
};
const OPENROUTER: LlmProvider = {
  id: "openrouter", kind: "custom", base_url: "https://openrouter.ai/api/v1", api_key_env: null, api_key_set: true,
  models: ["qwen/qwen3.5-9b", "z-ai/glm-5.3-flash"], params: { extra_body: { reasoning: { enabled: false } } },
  local: false, max_tokens_in_body: null, requests_per_minute: null, builtin: false,
};

function renderSection() {
  return render(
    <MantineProvider>
      <LlmProvidersSection />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listLlmProviders).mockResolvedValue([LOCAL, OPENROUTER]);
  vi.mocked(client.saveLlmProvider).mockResolvedValue(OPENROUTER);
  vi.mocked(client.deleteLlmProvider).mockResolvedValue({ deleted: "openrouter" });
  vi.mocked(client.testLlmProvider).mockResolvedValue({
    ok: true, answer: "OK", latency_ms: 420,
    usage: { calls: 1, input_tokens: 12, output_tokens: 1, reasoning_tokens: 0 },
  });
});

describe("LlmProvidersSection", () => {
  it("lists built-in and configured providers without showing keys", async () => {
    renderSection();
    expect(await screen.findByText("openrouter")).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
    expect(screen.getAllByText(/chave configurada/).length).toBe(2);
    // built-ins cannot be edited or removed
    expect(screen.getAllByRole("button", { name: "Remover" })).toHaveLength(1);
  });

  it("saves a new custom provider with its models and extra parameters", async () => {
    renderSection();
    await screen.findByText("openrouter");
    fireEvent.change(screen.getByLabelText(/Id do provedor/), { target: { value: "deepseek" } });
    fireEvent.change(screen.getByLabelText(/Base URL/), { target: { value: "https://api.deepseek.com/v1" } });
    fireEvent.change(screen.getByLabelText(/Chave de API/), { target: { value: "sk-1" } });
    fireEvent.change(screen.getByLabelText(/Modelos/), { target: { value: "deepseek-v4.1-flash\n" } });
    fireEvent.change(screen.getByLabelText(/Parâmetros extras/), { target: { value: '{"extra_body": {"x": 1}}' } });
    await userEvent.click(screen.getByRole("button", { name: "Salvar provedor" }));
    await waitFor(() => expect(client.saveLlmProvider).toHaveBeenCalled());
    expect(vi.mocked(client.saveLlmProvider).mock.calls[0]).toEqual([
      "deepseek",
      {
        kind: "custom", base_url: "https://api.deepseek.com/v1", api_key: "sk-1", api_key_env: null,
        models: ["deepseek-v4.1-flash"], params: { extra_body: { x: 1 } }, local: false,
        requests_per_minute: null,
      },
    ]);
    expect(await screen.findByText("Provedor salvo")).toBeInTheDocument();
  });

  it("refuses invalid JSON in the extra parameters", async () => {
    renderSection();
    await screen.findByText("openrouter");
    fireEvent.change(screen.getByLabelText(/Id do provedor/), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText(/Parâmetros extras/), { target: { value: "{nope" } });
    await userEvent.click(screen.getByRole("button", { name: "Salvar provedor" }));
    expect(await screen.findByText(/JSON válido/)).toBeInTheDocument();
    expect(client.saveLlmProvider).not.toHaveBeenCalled();
  });

  it("edits keeping the stored key and tests a model", async () => {
    renderSection();
    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));
    expect(screen.getByLabelText(/Id do provedor/)).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Salvar provedor" }));
    await waitFor(() => expect(client.saveLlmProvider).toHaveBeenCalled());
    expect(vi.mocked(client.saveLlmProvider).mock.calls[0][1].api_key).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Testar" }));
    expect(await screen.findByText(/Respondeu "OK" em 420 ms/)).toBeInTheDocument();
    expect(client.testLlmProvider).toHaveBeenCalledWith("openrouter", "qwen/qwen3.5-9b");
  });

  it("removes a configured provider", async () => {
    renderSection();
    await userEvent.click(await screen.findByRole("button", { name: "Remover" }));
    expect(client.deleteLlmProvider).toHaveBeenCalledWith("openrouter");
  });
});
