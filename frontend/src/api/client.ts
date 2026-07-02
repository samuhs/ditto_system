import type {
  ChatConfig,
  ChatConfigInput,
  ChatMessage,
  ChatTurn,
  ExperimentDetail,
  ExperimentRef,
  ExperimentSummary,
  IngestResult,
  Options,
  PromptsResponse,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (body?.detail) {
        message = typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
      }
    } catch { /* ignore parse errors, keep HTTP status message */ }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function getOptions(): Promise<Options> {
  return asJson<Options>(await fetch(`${BASE}/options`));
}

export async function ingest(form: FormData): Promise<IngestResult> {
  return asJson<IngestResult>(await fetch(`${BASE}/ingest`, { method: "POST", body: form }));
}

export async function createExperiment(form: FormData): Promise<ExperimentRef> {
  return asJson<ExperimentRef>(
    await fetch(`${BASE}/experiments`, { method: "POST", body: form }),
  );
}

export async function getExperiment(id: number): Promise<ExperimentDetail> {
  return asJson<ExperimentDetail>(await fetch(`${BASE}/experiments/${id}`));
}

export async function pauseExperiment(id: number): Promise<{ id: number; status: string }> {
  return asJson(await fetch(`${BASE}/experiments/${id}/pause`, { method: "POST" }));
}

export async function listExperiments(): Promise<ExperimentSummary[]> {
  return asJson<ExperimentSummary[]>(await fetch(`${BASE}/experiments`));
}

export async function getPrompts(): Promise<PromptsResponse> {
  return asJson<PromptsResponse>(await fetch(`${BASE}/prompts`));
}

export async function savePrompt(
  technique: string,
  key: string,
  text: string,
): Promise<{ technique: string; key: string; text: string }> {
  return asJson(
    await fetch(`${BASE}/prompts/${technique}/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  );
}

export async function getPersonas(): Promise<{ personas: string[] }> {
  return asJson(await fetch(`${BASE}/personas`));
}

export async function listChatConfigs(): Promise<ChatConfig[]> {
  return asJson<ChatConfig[]>(await fetch(`${BASE}/chat-configs`));
}

export async function createChatConfig(config: ChatConfigInput): Promise<{ id: number; name: string }> {
  return asJson(await fetch(`${BASE}/chat-configs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  }));
}

export async function deleteChatConfig(id: number): Promise<{ id: number; deleted: boolean }> {
  return asJson(await fetch(`${BASE}/chat-configs/${id}`, { method: "DELETE" }));
}

export async function sendChat(configId: number, messages: ChatMessage[]): Promise<ChatTurn> {
  return asJson<ChatTurn>(await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_id: configId, messages }),
  }));
}

export async function saveDialogue(configId: number, messages: ChatMessage[]): Promise<{ id: number }> {
  return asJson(await fetch(`${BASE}/dialogues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_id: configId, messages }),
  }));
}
