import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { TasksProvider } from "../context/TasksContext";
import { ExperimentPage } from "./ExperimentPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MemoryRouter>
      <MantineProvider>
        <TasksProvider>
          <ExperimentPage />
        </TasksProvider>
      </MantineProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["teste-1"],
    base_indexes: {
      "teste-1": [
        { chunking: "fixed", embedding: "e5" },
        { chunking: "recursive", embedding: "gemini" },
      ],
    },
    chunkings: ["recursive", "fixed", "token"],
    embeddings: ["gemini", "e5"],
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

  it("sends concurrency 1 by default", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /preencher tudo/i }));
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    const form = vi.mocked(client.createExperiment).mock.calls[0][0] as FormData;
    expect(JSON.parse(form.get("config") as string).concurrency).toBe(1);
  });

  it("lists real model names with a subtle local/remote tag", async () => {
    vi.mocked(client.getOptions).mockResolvedValue({
      bases: ["teste-1"], chunkings: ["recursive"], embeddings: ["gemini"],
      llms: ["gemini-2.5-flash-lite", "qwen2.5:3b-instruct"],
      llm_options: [
        { value: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite", location: "remote" },
        { value: "qwen2.5:3b-instruct", label: "qwen2.5:3b-instruct", location: "local" },
      ],
      rags: ["naive"], retrievers: ["similarity"], metrics: ["answer_relevancy"],
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(screen.getByRole("textbox", { name: /^llms$/i }));
    expect(await screen.findByText("qwen2.5:3b-instruct")).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
    expect(screen.getByText("remoto")).toBeInTheDocument();
  });

  it("offers only the indexes of the chosen base, all preselected, and submits the pairs", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("button", { name: /preencher tudo/i });
    await user.click(screen.getByRole("textbox", { name: /^base$/i }));
    await user.click(await screen.findByRole("option", { name: "teste-1" }));
    expect(screen.getAllByText("fixed · e5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("recursive · gemini").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /indexar mais variações/i })).toHaveAttribute(
      "href",
      "/ingest?base=teste-1",
    );
    await user.click(screen.getByRole("button", { name: /gerar/i }));
    await waitFor(() => expect(client.createExperiment).toHaveBeenCalled());
    const form = vi.mocked(client.createExperiment).mock.calls[0][0] as FormData;
    const config = JSON.parse(form.get("config") as string);
    expect(config.indexes).toEqual([
      { chunking: "fixed", embedding: "e5" },
      { chunking: "recursive", embedding: "gemini" },
    ]);
    expect(config.chunkings).toEqual(["fixed", "recursive"]);
    expect(config.embeddings).toEqual(["e5", "gemini"]);
  });
});
