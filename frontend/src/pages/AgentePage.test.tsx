import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { AgentePage } from "./AgentePage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <AgentePage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getFlow).mockResolvedValue({
    nodes: [
      { id: "triage", label: "Triagem", type: "prompt", description: "d", prompt: "Mensagem: {question}", required_placeholders: ["question"] },
      { id: "rag", label: "RAG", type: "rag", description: "usa a técnica" },
    ],
    edges: [{ source: "triage", target: "rag", label: "precisa" }],
  });
  vi.mocked(client.getPersonas).mockResolvedValue({ personas: ["travel_guide"] });
  vi.mocked(client.getPersona).mockResolvedValue({ name: "travel_guide", text: "guia" });
  vi.mocked(client.savePersona).mockResolvedValue({ name: "travel_guide", text: "novo" });
  vi.mocked(client.saveFlowPrompt).mockResolvedValue({ node: "triage", text: "x" });
});

describe("AgentePage", () => {
  it("loads and renders flow nodes", async () => {
    renderPage();
    expect(await screen.findByText("Triagem")).toBeInTheDocument();
    expect(await screen.findByText("RAG")).toBeInTheDocument();
  });

  it("edits and saves a persona in the Personas tab", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /personas/i }));
    const area = await screen.findByDisplayValue("guia");
    await user.clear(area);
    await user.type(area, "novo");
    await user.click(screen.getByRole("button", { name: /salvar persona/i }));
    await waitFor(() => expect(client.savePersona).toHaveBeenCalledWith("travel_guide", "novo"));
  });
});
