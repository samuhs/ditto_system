import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createExperiment,
  getExperiment,
  getOptions,
  getPrompts,
  ingest,
  listExperiments,
  savePrompt,
} from "./client";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("getOptions returns parsed options", async () => {
    const options = { chunkings: ["recursive"], embeddings: ["gemini"], llms: ["gemini"], rags: ["naive"], retrievers: ["similarity"], metrics: ["rouge_l"] };
    vi.stubGlobal("fetch", mockFetchOnce(options));
    await expect(getOptions()).resolves.toEqual(options);
    expect(fetch).toHaveBeenCalledWith("/api/options");
  });

  it("ingest posts form data and returns the result", async () => {
    const result = { collections: ["viagem__recursive__gemini"], total_chunks: 10 };
    const fetchMock = mockFetchOnce(result);
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    await expect(ingest(form)).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith("/api/ingest", { method: "POST", body: form });
  });

  it("createExperiment posts to the experiments endpoint and returns the ref", async () => {
    const ref = { id: 1, name: "kind-ember-89", status: "pending" };
    const fetchMock = mockFetchOnce(ref);
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    await expect(createExperiment(form)).resolves.toEqual(ref);
    expect(fetchMock).toHaveBeenCalledWith("/api/experiments", { method: "POST", body: form });
  });

  it("listExperiments returns the summary list", async () => {
    const summaries = [{ id: 1, name: "kind-ember-89", status: "done" }];
    vi.stubGlobal("fetch", mockFetchOnce(summaries));
    await expect(listExperiments()).resolves.toEqual(summaries);
    expect(fetch).toHaveBeenCalledWith("/api/experiments");
  });

  it("getExperiment returns the detail", async () => {
    const detail = { id: 1, name: "x", status: "done", results: [] };
    vi.stubGlobal("fetch", mockFetchOnce(detail));
    await expect(getExperiment(1)).resolves.toEqual(detail);
    expect(fetch).toHaveBeenCalledWith("/api/experiments/1");
  });

  it("throws on http error", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({}, false, 500));
    await expect(getOptions()).rejects.toThrow();
  });

  it("getPrompts fetches the prompts endpoint", async () => {
    const body = { naive: { answer: { text: "{context} {question}", required_placeholders: ["context", "question"] } } };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getPrompts()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/prompts");
  });

  it("savePrompt PUTs the new text", async () => {
    const fetchMock = mockFetchOnce({ technique: "naive", key: "answer", text: "t {context} {question}" });
    vi.stubGlobal("fetch", fetchMock);
    await savePrompt("naive", "answer", "t {context} {question}");
    expect(fetchMock).toHaveBeenCalledWith("/api/prompts/naive/answer", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "t {context} {question}" }),
    });
  });
});
