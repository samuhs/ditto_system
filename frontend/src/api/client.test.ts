import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createChatConfig,
  createExperiment,
  getDialogue,
  getExperiment,
  getFlow,
  getOptions,
  getPersona,
  getPersonas,
  getPrompts,
  ingest,
  listDialogues,
  listExperiments,
  saveDialogue,
  saveDialogueRating,
  saveFlowPrompt,
  savePersona,
  savePrompt,
  sendChat,
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

  it("listExperiments returns the paginated envelope", async () => {
    const body = {
      items: [{ id: 1, name: "kind-ember-89", status: "done", created_at: "2026-07-05T10:00:00" }],
      total: 1, page: 1, page_size: 20,
    };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(listExperiments()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/experiments?page=1&page_size=20");
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

  it("getPersonas fetches personas", async () => {
    const body = { personas: ["travel_guide", "assistant"] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getPersonas()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/personas");
  });

  it("createChatConfig posts the config", async () => {
    const cfg = { name: "c1", base: "viagem", chunking: "recursive", embedding: "gemini", retriever: "similarity", rag: "naive", llm: "gemini", persona: "travel_guide" };
    const fetchMock = mockFetchOnce({ id: 1, name: "c1" });
    vi.stubGlobal("fetch", fetchMock);
    await createChatConfig(cfg);
    expect(fetchMock).toHaveBeenCalledWith("/api/chat-configs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
  });

  it("sendChat posts config_id and messages", async () => {
    const fetchMock = mockFetchOnce({ reply: "olá", contexts: [] });
    vi.stubGlobal("fetch", fetchMock);
    await sendChat(1, [{ role: "user", content: "oi" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_id: 1, messages: [{ role: "user", content: "oi" }] }),
    });
  });

  it("saveDialogue posts the dialogue", async () => {
    const fetchMock = mockFetchOnce({ id: 7 });
    vi.stubGlobal("fetch", fetchMock);
    await saveDialogue(1, [{ role: "user", content: "oi" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/dialogues", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_id: 1, messages: [{ role: "user", content: "oi" }] }),
    });
  });

  it("getFlow fetches the flow spec", async () => {
    const body = { nodes: [{ id: "triage", label: "Triagem", type: "prompt", description: "d", prompt: "{question}", required_placeholders: ["question"] }], edges: [] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getFlow()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/chat/flow");
  });

  it("saveFlowPrompt PUTs the node prompt", async () => {
    const fetchMock = mockFetchOnce({ node: "triage", text: "t {question}" });
    vi.stubGlobal("fetch", fetchMock);
    await saveFlowPrompt("triage", "t {question}");
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/flow/triage", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "t {question}" }),
    });
  });

  it("getPersona fetches a persona", async () => {
    const fetchMock = mockFetchOnce({ name: "travel_guide", text: "guia" });
    vi.stubGlobal("fetch", fetchMock);
    await getPersona("travel_guide");
    expect(fetchMock).toHaveBeenCalledWith("/api/personas/travel_guide");
  });

  it("savePersona PUTs the persona text", async () => {
    const fetchMock = mockFetchOnce({ name: "travel_guide", text: "novo" });
    vi.stubGlobal("fetch", fetchMock);
    await savePersona("travel_guide", "novo");
    expect(fetchMock).toHaveBeenCalledWith("/api/personas/travel_guide", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "novo" }),
    });
  });

  it("listDialogues builds the query string", async () => {
    const body = { items: [], total: 0, page: 1, page_size: 20 };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(
      listDialogues({ page: 2, page_size: 20, rated: "unrated", sort: "rating_asc", date: "2026-03-10" }),
    ).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith(
      "/api/dialogues?page=2&page_size=20&date=2026-03-10&rated=unrated&sort=rating_asc",
    );
  });

  it("listDialogues with no params hits the bare endpoint", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({ items: [], total: 0, page: 1, page_size: 20 }));
    await listDialogues();
    expect(fetch).toHaveBeenCalledWith("/api/dialogues");
  });

  it("getDialogue fetches the detail", async () => {
    const body = { id: 5, created_at: "x", rating: null, config_snapshot: {}, messages: [] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getDialogue(5)).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/dialogues/5");
  });

  it("saveDialogueRating PUTs the rating", async () => {
    const fetchMock = mockFetchOnce({ id: 5, rating: 8 });
    vi.stubGlobal("fetch", fetchMock);
    await saveDialogueRating(5, 8);
    expect(fetchMock).toHaveBeenCalledWith("/api/dialogues/5/rating", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: 8 }),
    });
  });
});
