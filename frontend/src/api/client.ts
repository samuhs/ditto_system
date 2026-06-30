import type {
  ExperimentDetail,
  ExperimentRef,
  ExperimentSummary,
  IngestResult,
  Options,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`request failed with status ${response.status}`);
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

export async function listExperiments(): Promise<ExperimentSummary[]> {
  return asJson<ExperimentSummary[]>(await fetch(`${BASE}/experiments`));
}
