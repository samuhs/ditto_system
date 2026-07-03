import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { ExperimentPage } from "./ExperimentPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <TasksProvider>
        <ExperimentPage />
      </TasksProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["teste-1"],
    chunkings: ["recursive"],
    embeddings: ["gemini"],
    llms: ["gemini"],
    rags: ["naive"],
    retrievers: ["similarity"],
    metrics: ["answer_relevancy"],
  });
  vi.mocked(client.createExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "pending" });
  vi.mocked(client.getExperiment).mockResolvedValue({ id: 7, name: "kind-ember-89", status: "done", results: [] });
});

describe("ExperimentPage", () => {
  it("calls createExperiment when Gerar is clicked", async () => {
    renderPage();
    const user = userEvent.setup();
    // wait for options to load, then submit
    await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() =>
      expect(client.createExperiment).toHaveBeenCalledWith(expect.any(FormData)),
    );
  });

  it("fills all 5 fields when 'Preencher tudo' is clicked and clears on 'Limpar tudo'", async () => {
    renderPage();
    const user = userEvent.setup();
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    expect(fillBtn).toBeEnabled();
    await user.click(fillBtn);
    expect(screen.getByRole("button", { name: /limpar tudo/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /limpar tudo/i }));
    expect(screen.getByRole("button", { name: /preencher tudo/i })).toBeInTheDocument();
  });

  it("includes llms in the submitted config", async () => {
    renderPage();
    const user = userEvent.setup();
    const fillBtn = await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(fillBtn);
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    const form = vi.mocked(client.createExperiment).mock.calls[0][0] as FormData;
    const config = JSON.parse(form.get("config") as string);
    expect(config.llms).toEqual(["gemini"]);
  });
});
