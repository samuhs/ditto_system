import type {
  RetestAgreement,
  AnnotationValidation,
  AdjudicationView,
  FinalNotes,
  AnnotationAgreement,
  AnnotationNoteValues,
  AnnotationQueue,
  AnnotationRoundDetail,
  AnnotationRoundInput,
  AnnotationRoundPreview,
  AnnotationRoundSummary,
  Annotator,
  AppSettings,
  Comparison,
  BaseSummary,
  EvaluationSettings,
  MemoryStatus,
  ChatConfig,
  ChatConfigInput,
  ChatMessage,
  ChatTurn,
  DialogueDetail,
  DialogueList,
  DialogueListParams,
  ExperimentDetail,
  ExperimentDifficulty,
  ExperimentList,
  GraphBuildJob,
  GraphBuildRequest,
  ExperimentRef,
  FlowSpec,
  IngestResult,
  Options,
  PairAdjudicationView,
  PairwiseAgreement,
  PairwiseNoteValues,
  PairwisePreference,
  PairwiseQueue,
  PairwiseSummary,
  Persona,
  PromptsResponse,
  Rubric,
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

/** Every Base with its Índices and the Grafos de conhecimento built from them. */
export async function listBases(): Promise<BaseSummary[]> {
  return asJson<BaseSummary[]>(await fetch(`${BASE}/bases`));
}

/** Deletes a Base; refused (409, with the reason) while an experiment uses it. */
export async function deleteBase(name: string): Promise<{ base: string; deleted: string[] }> {
  return asJson(await fetch(`${BASE}/bases/${encodeURIComponent(name)}`, { method: "DELETE" }));
}

export async function createExperiment(form: FormData): Promise<ExperimentRef> {
  return asJson<ExperimentRef>(
    await fetch(`${BASE}/experiments`, { method: "POST", body: form }),
  );
}

/** Builds the Grafos de conhecimento of a Base's Índices in the background. */
export async function startGraphBuild(body: GraphBuildRequest): Promise<GraphBuildJob> {
  return asJson<GraphBuildJob>(await fetch(`${BASE}/graph-builds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

/** The Grafo build jobs of the API process (of one Base, if given), newest first. */
export async function listGraphBuilds(base?: string): Promise<GraphBuildJob[]> {
  const query = base ? `?base=${encodeURIComponent(base)}` : "";
  return asJson<GraphBuildJob[]>(await fetch(`${BASE}/graph-builds${query}`));
}

export async function getGraphBuild(id: number): Promise<GraphBuildJob> {
  return asJson<GraphBuildJob>(await fetch(`${BASE}/graph-builds/${id}`));
}

/** Stops the build at its next chunk; the chunks already extracted stay cached. */
export async function pauseGraphBuild(id: number): Promise<GraphBuildJob> {
  return asJson<GraphBuildJob>(await fetch(`${BASE}/graph-builds/${id}/pause`, { method: "POST" }));
}

/** Runs a paused (or failed) build again, extracting only the chunks still missing. */
export async function resumeGraphBuild(id: number): Promise<GraphBuildJob> {
  return asJson<GraphBuildJob>(await fetch(`${BASE}/graph-builds/${id}/resume`, { method: "POST" }));
}

export async function getExperiment(id: number): Promise<ExperimentDetail> {
  return asJson<ExperimentDetail>(await fetch(`${BASE}/experiments/${id}`));
}

export async function getExperimentDifficulty(id: number, metric?: string): Promise<ExperimentDifficulty> {
  const query = metric ? `?metric=${encodeURIComponent(metric)}` : "";
  return asJson<ExperimentDifficulty>(await fetch(`${BASE}/experiments/${id}/difficulty${query}`));
}

export function exportExperimentUrl(id: number): string {
  return `${BASE}/experiments/${id}/export.csv`;
}

export async function pauseExperiment(id: number): Promise<{ id: number; status: string }> {
  return asJson(await fetch(`${BASE}/experiments/${id}/pause`, { method: "POST" }));
}

/** Retomada: resume a paused or failed experiment, rerunning only what is missing.
 *
 * `concurrency` optionally lowers the experiment's concorrência before it runs again
 * (1 <= concurrency <= the experiment's current one; the API answers 422 outside that
 * range). Omitted, the concorrência stays whatever it already was.
 */
export async function resumeExperiment(
  id: number,
  concurrency?: number,
): Promise<{ id: number; status: string }> {
  const init: RequestInit = { method: "POST" };
  if (concurrency !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify({ concurrency });
  }
  return asJson(await fetch(`${BASE}/experiments/${id}/resume`, init));
}

function comparisonQuery(items: string[], baseline?: string | null, metric?: string | null): string {
  const params = new URLSearchParams({ items: items.join(",") });
  if (baseline) params.set("baseline", baseline);
  if (metric) params.set("metric", metric);
  return params.toString();
}

export async function getComparison(
  items: string[], baseline?: string | null, metric?: string | null,
): Promise<Comparison> {
  return asJson<Comparison>(await fetch(`${BASE}/comparisons?${comparisonQuery(items, baseline, metric)}`));
}

/** Download URL of the Comparação as CSV or LaTeX (the same calculation the page shows). */
export function comparisonExportUrl(
  format: "csv" | "tex", items: string[], baseline?: string | null, metric?: string | null,
): string {
  return `${BASE}/comparisons/export.${format}?${comparisonQuery(items, baseline, metric)}`;
}

export async function listExperiments(page = 1, pageSize = 20, base?: string): Promise<ExperimentList> {
  const query = base ? `&base=${encodeURIComponent(base)}` : "";
  return asJson<ExperimentList>(await fetch(`${BASE}/experiments?page=${page}&page_size=${pageSize}${query}`));
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

export async function getFlow(): Promise<FlowSpec> {
  return asJson<FlowSpec>(await fetch(`${BASE}/chat/flow`));
}

export async function saveFlowPrompt(node: string, text: string): Promise<{ node: string; text: string }> {
  return asJson(await fetch(`${BASE}/chat/flow/${node}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  }));
}

export async function getPersona(name: string): Promise<Persona> {
  return asJson<Persona>(await fetch(`${BASE}/personas/${name}`));
}

export async function savePersona(name: string, text: string): Promise<Persona> {
  return asJson<Persona>(await fetch(`${BASE}/personas/${name}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  }));
}

export async function listDialogues(params: DialogueListParams = {}): Promise<DialogueList> {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.date) q.set("date", params.date);
  if (params.rated) q.set("rated", params.rated);
  if (params.sort) q.set("sort", params.sort);
  const qs = q.toString();
  return asJson<DialogueList>(await fetch(`${BASE}/dialogues${qs ? `?${qs}` : ""}`));
}

export async function getDialogue(id: number): Promise<DialogueDetail> {
  return asJson<DialogueDetail>(await fetch(`${BASE}/dialogues/${id}`));
}

export async function saveDialogueRating(
  id: number,
  rating: number,
): Promise<{ id: number; rating: number }> {
  return asJson(await fetch(`${BASE}/dialogues/${id}/rating`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  }));
}

export async function getMemory(): Promise<MemoryStatus> {
  return asJson<MemoryStatus>(await fetch(`${BASE}/system/memory`));
}

export async function getSettings(): Promise<AppSettings> {
  return asJson<AppSettings>(await fetch(`${BASE}/settings`));
}

export async function saveGeminiKey(key: string): Promise<{ gemini_api_key_set: boolean }> {
  return asJson(await fetch(`${BASE}/settings/gemini-key`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  }));
}

export async function getEvaluationSettings(): Promise<EvaluationSettings> {
  return asJson<EvaluationSettings>(await fetch(`${BASE}/settings/evaluation`));
}

export async function saveEvalEmbedding(name: string): Promise<{ eval_embedding: string }> {
  return asJson(await fetch(`${BASE}/settings/eval-embedding`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }));
}

export async function saveStallLimit(minutes: number): Promise<{ stall_limit_minutes: number }> {
  return asJson(await fetch(`${BASE}/settings/stall-limit`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ minutes }),
  }));
}

// ---- Anotação humana ----

const json = (body: unknown) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/** Avaliadores by name; `active` filters active or inactive ones. */
export async function listAnnotators(active?: boolean): Promise<Annotator[]> {
  const query = active === undefined ? "" : `?active=${active}`;
  return asJson<Annotator[]>(await fetch(`${BASE}/annotators${query}`));
}

/** Registers a new Avaliador; refused (409) when the name is taken. */
export async function createAnnotator(name: string): Promise<Annotator> {
  return asJson<Annotator>(await fetch(`${BASE}/annotators`, { method: "POST", ...json({ name }) }));
}

export async function setAnnotatorActive(id: number, active: boolean): Promise<Annotator> {
  return asJson<Annotator>(await fetch(`${BASE}/annotators/${id}`, { method: "PATCH", ...json({ active }) }));
}

export async function getRubric(): Promise<Rubric> {
  return asJson<Rubric>(await fetch(`${BASE}/annotation/rubric`));
}

export async function listAnnotationRounds(): Promise<AnnotationRoundSummary[]> {
  return asJson<AnnotationRoundSummary[]>(await fetch(`${BASE}/annotation/rounds`));
}

export async function createAnnotationRound(body: AnnotationRoundInput): Promise<AnnotationRoundSummary> {
  return asJson<AnnotationRoundSummary>(await fetch(`${BASE}/annotation/rounds`, { method: "POST", ...json(body) }));
}

/** How many answers each stratum has and would give, without creating the Rodada. */
export async function previewAnnotationRound(body: AnnotationRoundInput): Promise<AnnotationRoundPreview> {
  return asJson<AnnotationRoundPreview>(
    await fetch(`${BASE}/annotation/rounds/preview`, { method: "POST", ...json(body) }),
  );
}

export async function getAnnotationRound(id: number): Promise<AnnotationRoundDetail> {
  return asJson<AnnotationRoundDetail>(await fetch(`${BASE}/annotation/rounds/${id}`));
}

/** The Avaliador joins an open Rodada (idempotent). */
export async function joinAnnotationRound(roundId: number, annotatorId: number): Promise<void> {
  await asJson(await fetch(`${BASE}/annotation/rounds/${roundId}/participants`, {
    method: "POST", ...json({ annotator_id: annotatorId }),
  }));
}

/** Removes an Avaliador from a Rodada together with their notes in it. */
export async function removeAnnotationParticipant(
  roundId: number, annotatorId: number,
): Promise<{ round_id: number; annotator_id: number; notes_deleted: number }> {
  return asJson(await fetch(`${BASE}/annotation/rounds/${roundId}/participants/${annotatorId}`, { method: "DELETE" }));
}

/** A Rodada as one Avaliador sees it: blind, with only that Avaliador's notes. */
export async function getAnnotationQueue(roundId: number, annotatorId: number): Promise<AnnotationQueue> {
  return asJson<AnnotationQueue>(
    await fetch(`${BASE}/annotation/rounds/${roundId}/queue?annotator_id=${annotatorId}`),
  );
}

export async function saveAnnotationNote(
  itemId: number, annotatorId: number, note: AnnotationNoteValues,
): Promise<AnnotationNoteValues & { item_id: number; annotator_id: number }> {
  return asJson(await fetch(`${BASE}/annotation/items/${itemId}/notes/${annotatorId}`, { method: "PUT", ...json(note) }));
}

/** Freezes the notes of a Rodada for the analysis. */
export async function closeAnnotationRound(id: number): Promise<AnnotationRoundSummary> {
  return asJson<AnnotationRoundSummary>(await fetch(`${BASE}/annotation/rounds/${id}/close`, { method: "POST" }));
}

/** Concordância between the Avaliadores of a Rodada (kappa, alpha, disagreements); a pairwise
 * Rodada's has a different shape (`dimension` instead of `dimensions`), told apart by
 * `round.kind`. */
export async function getAnnotationAgreement(id: number): Promise<AnnotationAgreement | PairwiseAgreement> {
  return asJson(await fetch(`${BASE}/annotation/rounds/${id}/agreement`));
}

/** Designates (or clears, with null) the Rodada's adjudicator. */
export async function setAnnotationAdjudicator(roundId: number, annotatorId: number | null): Promise<AnnotationRoundSummary> {
  return asJson<AnnotationRoundSummary>(await fetch(`${BASE}/annotation/rounds/${roundId}`, {
    method: "PATCH", ...json({ adjudicator_id: annotatorId }),
  }));
}

/** The disputed Items of a closed Rodada, for its adjudicator only. */
export async function getAdjudication(roundId: number, annotatorId: number): Promise<AdjudicationView> {
  return asJson<AdjudicationView>(
    await fetch(`${BASE}/annotation/rounds/${roundId}/adjudication?annotator_id=${annotatorId}`),
  );
}

export async function saveAdjudication(
  itemId: number, annotatorId: number, decision: { correctness: number | null; grounding: number | null },
): Promise<{ item_id: number; correctness: number | null; grounding: number | null }> {
  return asJson(await fetch(`${BASE}/annotation/items/${itemId}/adjudication`, {
    method: "PUT", ...json({ annotator_id: annotatorId, ...decision }),
  }));
}

/** The Nota final of each Item and how many are still pending adjudication. */
export async function getFinalNotes(roundId: number): Promise<FinalNotes> {
  return asJson<FinalNotes>(await fetch(`${BASE}/annotation/rounds/${roundId}/final`));
}

/** The human Nota final against the automatic metrics (Spearman; means per Combinação and type). */
export async function getAnnotationValidation(roundId: number): Promise<AnnotationValidation> {
  return asJson<AnnotationValidation>(await fetch(`${BASE}/annotation/rounds/${roundId}/validation`));
}

/** A retest Rodada: the same Items for the same Avaliador, in a new order. */
export async function createRetest(roundId: number, annotatorId: number): Promise<AnnotationRoundSummary> {
  return asJson<AnnotationRoundSummary>(await fetch(`${BASE}/annotation/rounds/${roundId}/retest`, {
    method: "POST", ...json({ annotator_id: annotatorId }),
  }));
}

/** Intra-rater alpha between each Avaliador's first pass and their retest. */
export async function getRetests(roundId: number): Promise<RetestAgreement[]> {
  return asJson<RetestAgreement[]>(await fetch(`${BASE}/annotation/rounds/${roundId}/retests`));
}

/** Download URL of a Rodada's notes (CSV, plain or for Excel) or analysis tables (LaTeX: Portuguese
 * with point or comma decimals, or English for the English paper). */
export function annotationExportUrl(
  roundId: number, kind: "csv" | "tex", decimal: "point" | "comma" = "point", excel = false, lang: "pt" | "en" = "pt",
): string {
  const params = new URLSearchParams();
  if (kind === "tex" && lang === "en") params.set("lang", "en");
  else if (kind === "tex" && decimal === "comma") params.set("decimal", "comma");
  if (kind === "csv" && excel) params.set("excel", "true");
  const query = params.toString();
  return `${BASE}/annotation/rounds/${roundId}/export.${kind}${query ? `?${query}` : ""}`;
}

/** Deletes a Rodada created by mistake; refused (409) once it has any notes. */
export async function deleteAnnotationRound(roundId: number): Promise<{ round_id: number; deleted: boolean }> {
  return asJson(await fetch(`${BASE}/annotation/rounds/${roundId}`, { method: "DELETE" }));
}

// ---- Pairwise (side-by-side) comparison Rodadas ----

/** A pairwise Rodada as one Avaliador sees it: blind, with only that Avaliador's notes. */
export async function getPairwiseQueue(roundId: number, annotatorId: number): Promise<PairwiseQueue> {
  return asJson<PairwiseQueue>(
    await fetch(`${BASE}/annotation/rounds/${roundId}/queue?annotator_id=${annotatorId}`),
  );
}

export async function savePairwiseNote(
  itemId: number, annotatorId: number, note: PairwiseNoteValues,
): Promise<PairwiseNoteValues & { item_id: number; annotator_id: number }> {
  return asJson(await fetch(`${BASE}/annotation/pair-items/${itemId}/notes/${annotatorId}`, {
    method: "PUT", ...json(note),
  }));
}

/** The disputed Items of a closed pairwise Rodada, for its adjudicator only. */
export async function getPairAdjudication(roundId: number, annotatorId: number): Promise<PairAdjudicationView> {
  return asJson<PairAdjudicationView>(
    await fetch(`${BASE}/annotation/rounds/${roundId}/pair-adjudication?annotator_id=${annotatorId}`),
  );
}

export async function savePairAdjudication(
  itemId: number, annotatorId: number, preference: PairwisePreference,
): Promise<{ item_id: number; preference: PairwisePreference }> {
  return asJson(await fetch(`${BASE}/annotation/pair-items/${itemId}/adjudication`, {
    method: "PUT", ...json({ annotator_id: annotatorId, preference }),
  }));
}

/** Per Avaliador, and for the final preference: wins of each Combinação, ties, a sign test
 * p-value, each side's win proportion with a 95% Wilson CI, and reason counts. The only call
 * that unblinds which Combinação is which. */
export async function getPairwiseSummary(roundId: number): Promise<PairwiseSummary> {
  return asJson<PairwiseSummary>(await fetch(`${BASE}/annotation/rounds/${roundId}/pairwise-summary`));
}
