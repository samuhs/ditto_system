import { afterEach, describe, expect, it, vi } from "vitest";

import { createExperiment, getExperiment, getOptions, ingest } from "./client";

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

  it("createExperiment returns the experiment ref", async () => {
    const ref = { id: 1, name: "kind-ember-89", status: "pending" };
    vi.stubGlobal("fetch", mockFetchOnce(ref));
    const form = new FormData();
    await expect(createExperiment(form)).resolves.toEqual(ref);
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
});
