export interface LlmOption {
  value: string;
  label: string;
  location: "local" | "remote";
}

export interface IndexPair {
  chunking: string;
  embedding: string;
}

/** An Índice in /options: the LLM extratores with a current Grafo de conhecimento of it. */
export interface IndexOption extends IndexPair {
  graph_extractors?: string[];
}

export interface Options {
  bases: string[];
  base_indexes?: Record<string, IndexOption[]>;
  chunkings: string[];
  embeddings: string[];
  llm_options: LlmOption[];
  rags: string[];
  retrievers: string[];
  metrics: string[];
}

export interface IngestResult {
  collections: string[];
  total_chunks: number;
  /** Índices that came out degenerate (a long document stored as one chunk). */
  warnings?: string[];
  /** The Grafo de conhecimento build queued after the Índices; null without one. */
  graph_build?: GraphBuildJob | null;
}

/** One Índice of a Grafo build: its state and chunks extracted / total. */
export interface IndexBuild {
  chunking: string;
  embedding: string;
  status: "pending" | "building" | "done" | "failed";
  extracted: number;
  total: number;
  stats: GraphStats | null;
  error: string | null;
}

/** A background build of the Grafos of some Índices of a Base by one LLM extrator. */
export interface GraphBuildJob {
  id: number;
  base: string;
  extractor: string;
  indexes: IndexBuild[];
  status: "pending" | "running" | "paused" | "done" | "failed";
  pause_requested: boolean;
  created_at: string;
  finished_at: string | null;
}

export interface GraphBuildRequest {
  base: string;
  extractor: string;
  /** Omitted: every Índice of the Base. */
  indexes?: IndexPair[];
}

/** A finished Grafo de conhecimento of an Índice, built by one LLM extrator. */
export interface GraphSummary {
  extractor: string;
  entities: number;
  relations: number;
  /** Share (0–100) of the extraction lines that could not be read. */
  failed_pct: number;
  /** ISO timestamp; null for a Grafo built before the date was recorded. */
  built_at: string | null;
}

/** An Índice (corte × embedding) of a Base. */
export interface IndexSummary {
  chunking: string;
  embedding: string;
  chunks: number;
  graphs: GraphSummary[];
}

/** A Base; `in_use` says why it cannot be deleted now (null: it can). */
export interface BaseSummary {
  name: string;
  indexes: IndexSummary[];
  in_use: string | null;
  /** Grafo builds still running, queued or paused, with their progress. */
  graph_builds?: GraphBuildJob[];
}

export interface ExperimentRef {
  id: number;
  name: string;
  status: string;
  /** Memory limits the experiment will hit under the active profile (PT-BR). */
  warnings?: string[];
}

export interface ExperimentSummary {
  id: number;
  name: string;
  status: string;
  /** The Base it ran on (null on experiments with no recorded config). */
  base?: string | null;
  created_at: string;
}

/** One Combinação of an Experimento, with the id a Comparação refers to it by. */
export interface ExperimentRunRef {
  id: number;
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
  status: string;
}

export interface ExperimentList {
  items: ExperimentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface RetrievedChunk {
  text: string;
  /** Retriever similarity; null for chunks with no score (e.g. a compression extract). */
  score: number | null;
  source: string | null;
}

export interface ExperimentResultRow {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
  question: string;
  answer: string;
  /** The chunks the answer was generated from, in rank order; absent on older payloads. */
  contexts?: RetrievedChunk[];
  scores: Record<string, number>;
  latency_ms: number;
  tokens: number;
  /** "simples" | "ponte" | "comparacao" | "agregacao"; absent on older payloads. */
  question_type?: string;
  /** Hop (1-based) of each reference evidence passage. */
  evidence_hops?: number[];
  bridge_entities?: string[];
  /** Whether each hop's evidence was retrieved (only when context_all_hops is scored). */
  hops_found?: { hop: number; found: boolean }[];
  /** GraphRAG runs: stats of the Grafo de conhecimento used; null for other techniques. */
  graph_stats?: GraphStats | null;
  /** GraphRAG results: entities the Grafo found and facts it used; null otherwise. */
  graph_explanation?: GraphExplanation | null;
  /** Whether the Grafo found each annotated Entidade-ponte (GraphRAG results only). */
  bridges_found?: { entity: string; found: boolean }[];
}

export interface GraphExplanation {
  /** hop 0: linked to the question; hop 1: a neighbour of a linked entity. */
  entities: { name: string; score: number; hop: number }[];
  facts: string[];
}

export interface GraphStats {
  entities: number;
  relations: number;
  /** Chunks of the Índice the graph was extracted from. */
  chunks: number;
  /** Extraction lines the LLM wrote, and how many of them could not be read. */
  lines: number;
  failed_lines: number;
  /** Chunks whose extraction call failed. */
  failed_chunks: number;
  /** The LLM extrator that built the Grafo (experiment rows). */
  extractor?: string;
}

export interface ExperimentProgress {
  completed: number;
  total: number;
  /** Staged runs: "generating", then "evaluating" while the answers are scored. */
  phase?: string | null;
  /** Answers scored so far in the evaluation stage, out of to_score. */
  scored?: number;
  to_score?: number;
  /** Seconds left at the scoring pace so far; null until the first batch. */
  eta_s?: number | null;
}

/** One Combinação + pergunta that was mid-call when a Pausa entry was recorded. */
export interface PauseInFlightItem {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
  question: string;
}

/** One entry of the Registro de pausa (the experiment's Pausa history). */
export interface PauseEntry {
  paused_at: string;
  /** "manual" | "stall" | "consecutive_failures" | "interrupted" | "failed". */
  reason: string;
  phase?: string | null;
  in_flight: PauseInFlightItem[];
  last_error?: { message: string; traceback: string } | null;
  memory: { free_mb: number; api_mb: number };
  /** Filled in once the experiment resumes (issue #17); null until then. */
  resumed_at?: string | null;
}

export interface ExperimentDetail {
  id: number;
  name: string;
  status: string;
  runs?: ExperimentRunRef[];
  created_at?: string;
  finished_at?: string;
  pause_requested?: boolean;
  error?: string | null;
  /** Embedder that scored this experiment's answers (absent on old runs). */
  eval_embedding?: string | null;
  /** The LLM extrator whose Grafos graph/graph_mix queried; null without them. */
  graph_extractor?: string | null;
  progress?: ExperimentProgress;
  results: ExperimentResultRow[];
  prompts?: Record<string, Record<string, string>>;
  /** Registro de pausa: every Pausa this experiment has had, oldest first. */
  pauses?: PauseEntry[];
  /** Whether POST /resume would currently succeed (paused/failed, with questions recorded). */
  resumable?: boolean;
  /** Why it is not resumable right now; absent/null when `resumable` is true. */
  resumable_reason?: string | null;
  /** The config's current concorrência: the max a Retomada's concurrency field accepts. */
  concurrency?: number | null;
  /** Sampling temperature the experiment's LLMs used; null/absent: the provider's default. */
  temperature?: number | null;
  /** Cap on tokens per generation; null/absent: no explicit cap. */
  max_tokens?: number | null;
}

export interface PromptInfo {
  text: string;
  required_placeholders: string[];
}

export type PromptsResponse = Record<string, Record<string, PromptInfo>>;

export interface ChatConfig {
  id: number;
  name: string;
  base: string;
  chunking: string;
  embedding: string;
  retriever: string;
  rag: string;
  llm: string;
  persona: string;
}

export type ChatConfigInput = Omit<ChatConfig, "id">;

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatTurn {
  reply: string;
  contexts: string[];
  /** Signals of how hard the question looks: before retrieval and from the chunk scores. */
  difficulty?: TurnDifficulty;
  /** The standalone question the documents were searched with; null when there was no search. */
  query?: string | null;
}

export interface TurnDifficulty {
  question: Record<string, number>;
  retrieval: Record<string, number>;
}

export interface MetricSummary {
  mean: number;
  std: number;
  n: number;
}

export interface DifficultyCell {
  /** Each metric over the configurations that retrieve. */
  retrieval: Record<string, MetricSummary>;
  /** Each metric's mean without retrieval (closed book); empty if it did not run. */
  closed_book: Record<string, number>;
  /** Each metric's mean with the annotated evidence as context (oracle); empty if it did not run. */
  oracle: Record<string, number>;
  /** Share of retrievals that brought the annotated evidence back; null without evidence. */
  hit_rate: number | null;
  with_evidence: Record<string, number>;
  without_evidence: Record<string, number>;
}

export interface QuestionDifficulty {
  question: string;
  /** "simples" | "ponte" | "comparacao" | "agregacao"; absent on older payloads. */
  question_type?: string;
  signals: Record<string, number>;
  retrieval_signals: Record<string, number>;
  /** Signals that depend on the model but not on its answer, per LLM (perplexity). */
  model_signals: Record<string, Record<string, number>>;
  by_llm: Record<string, DifficultyCell>;
}

export interface IrtFit {
  metric: string;
  n_questions: number;
  n_configurations: number;
  /** False below min_questions: the estimates are only indicative. */
  reliable: boolean;
  min_questions: number;
  /** Rasch difficulty per question, centred at 0 (positive = harder than average). */
  difficulty: Record<string, number>;
  difficulty_by_llm: Record<string, Record<string, number>>;
  ability: Record<string, number>;
  /** Below this many questions a Tipo de pergunta gets no fit. */
  min_fit_questions?: number;
  /** One fit per Tipo de pergunta, each centred at 0 on its own questions. */
  by_type?: Record<string, IrtTypeFit>;
}

export interface IrtTypeFit {
  n_questions: number;
  reliable: boolean;
  /** Null when the type has too few questions for a fit. */
  difficulty: Record<string, number> | null;
  difficulty_by_llm: Record<string, Record<string, number>> | null;
}

export interface SignalCorrelation {
  signal: string;
  /** question: text, corpus or evidence; retrieval: chunk scores; model: per LLM (perplexity). */
  kind: "question" | "retrieval" | "model";
  /** Spearman's rho with the IRT difficulty; null when it cannot be computed. */
  overall: number | null;
  by_llm: Record<string, number | null>;
}

export interface SignalCorrelations {
  n_questions: number;
  reliable: boolean;
  rows: SignalCorrelation[];
}

export interface ExperimentDifficulty {
  llms: string[];
  metrics: string[];
  /** Metric the IRT fit used. */
  metric: string | null;
  questions: QuestionDifficulty[];
  irt: IrtFit | null;
  correlations: SignalCorrelations | null;
  /** LLMs whose perplexity was not computed, and why (too little memory, or an error). */
  perplexity_skipped?: Record<string, { free_mb?: number; needed_mb?: number; error?: string }>;
}

export interface FlowNode {
  id: string;
  label: string;
  type: "prompt" | "rag";
  description: string;
  prompt?: string;
  required_placeholders?: string[];
}

export interface FlowEdge {
  source: string;
  target: string;
  label: string;
}

export interface FlowSpec {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface Persona {
  name: string;
  text: string;
}

export interface DialogueListItem {
  id: number;
  created_at: string | null;
  rating: number | null;
  name: string | null;
  persona: string | null;
  message_count: number;
  preview: string | null;
}

export interface DialogueList {
  items: DialogueListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DialogueDetail {
  id: number;
  created_at: string | null;
  rating: number | null;
  config_snapshot: Record<string, string>;
  messages: ChatMessage[];
}

export interface DialogueListParams {
  page?: number;
  page_size?: number;
  date?: string | null;
  rated?: "all" | "rated" | "unrated";
  sort?: "recent" | "oldest" | "rating_asc" | "rating_desc";
}

export interface MemoryStatus {
  profile: { name: string; max_local_models: number; embedding_device: string; max_concurrency: number };
  total_bytes: number;
  available_bytes: number;
  /** Memory the API process uses (physical footprint on macOS, RSS elsewhere). */
  process_memory_bytes: number;
  loaded_models: { name: string; device: string; local: boolean; in_use: number }[];
}

export interface AppSettings {
  gemini_api_key_set: boolean;
  /** Travamento: minutes a running experiment may go without progress before it pauses itself. */
  stall_limit_minutes: number;
}

/** An LLM provider: any model behind any OpenAI-compatible URL or LangChain provider. */
export interface LlmProvider {
  id: string;
  /** "custom" (OpenAI-compatible URL) or a LangChain provider name (openai, google_genai, anthropic, ...). */
  kind: string;
  base_url: string | null;
  api_key_env: string | null;
  api_key_set: boolean;
  models: string[];
  /** Extra LangChain constructor arguments, e.g. {"extra_body": {"reasoning": {"enabled": false}}}. */
  params: Record<string, unknown>;
  local: boolean;
  max_tokens_in_body: boolean | null;
  /** Client-side cap on requests per minute to this provider; null: no cap. */
  requests_per_minute: number | null;
  builtin: boolean;
}

export interface LlmProviderInput {
  kind: string;
  base_url?: string | null;
  /** Omitted: keeps the stored key; "": clears it. */
  api_key?: string | null;
  api_key_env?: string | null;
  models: string[];
  params: Record<string, unknown>;
  local: boolean;
  requests_per_minute: number | null;
}

export interface LlmProviderTest {
  ok: boolean;
  answer?: string;
  latency_ms?: number;
  usage?: { calls: number; input_tokens: number; output_tokens: number; reasoning_tokens: number };
  error?: string;
}

export interface EvaluationSettings {
  /** Embedder that scores experiments that do not name one. */
  eval_embedding: string;
  embeddings: { name: string; local: boolean }[];
  metrics: { name: string; uses_embedding: boolean; requires_reference: boolean }[];
}

/** Difference of an item against the Linha de base, with its 95% bootstrap CI. */
export interface ComparisonDiff {
  mean: number;
  low: number;
  high: number;
  significant: boolean;
}

/** One Experimento × Combinação in a Comparação. */
export interface ComparisonItem {
  id: string;
  experiment_id: number;
  experiment_name: string;
  run_id: number;
  base: string;
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
  /** Its Experimento has not finished. */
  partial: boolean;
  /** Questions paired with the Linha de base (its own valid answers, for the Linha de base). */
  n: number;
  means: Record<string, number | null>;
  /** null for the Linha de base itself. */
  diff: ComparisonDiff | null;
}

/** Friedman over the questions every paired item scored, or why it could not run. */
export type ComparisonFriedman =
  | { chi2: number; df: number; p: number; n: number; reason?: undefined }
  | { reason: string };

/** A paired difference in one Tipo de pergunta, with its question count. */
export interface ComparisonTypeCell extends ComparisonDiff {
  n: number;
}

/** An item of another Base: its own mean and CI, never paired with the Linha de base. */
export interface ComparisonUnpaired extends Omit<ComparisonItem, "diff"> {
  mean: { mean: number; low: number; high: number };
}

export interface Comparison {
  other_bases: ComparisonUnpaired[];
  friedman: ComparisonFriedman;
  /** Each non-baseline item's difference per Tipo de pergunta; null where none paired. */
  by_type: { types: string[]; rows: { id: string; cells: Record<string, ComparisonTypeCell | null> }[] };
  baseline: string;
  metric: string;
  metrics: string[];
  base: string;
  items: ComparisonItem[];
  excluded: { id: string; reason: string }[];
}

// ---- Anotação humana ----

export interface Annotator {
  id: number;
  name: string;
  active: boolean;
}

export interface RubricLevel {
  value: number;
  label: string;
  description: string;
}

export interface RubricDimension {
  key: "correctness" | "grounding";
  label: string;
  question: string;
  levels: RubricLevel[];
}

export interface Rubric {
  version: number;
  dimensions: RubricDimension[];
}

/** "single": one answer scored on the Rubrica. "pairwise": two Combinações compared
 * side by side, with a preference instead of a score. */
export type AnnotationRoundKind = "single" | "pairwise";

export interface AnnotationRoundSummary {
  id: number;
  name: string;
  description: string;
  status: "open" | "closed";
  seed: number;
  rubric_version: number;
  experiment_ids: number[];
  size: number;
  kind: AnnotationRoundKind;
  /** A pilot Rodada calibrates the Rubrica and never enters the analysis. */
  pilot: boolean;
  strata: AnnotationStratumDim[];
  allocation: "proportional" | "equal";
  /** Who decides the Nota final where the Avaliadores disagree. */
  adjudicator_id: number | null;
  /** Set on a retest Rodada: the original Rodada and the Avaliador who repeats it. */
  source_round_id: number | null;
  retest_annotator_id: number | null;
  created_at: string | null;
}

export type AnnotationStratumDim = "question_type" | "rag" | "llm";

export interface AnnotationStratumPreview {
  key: Partial<Record<AnnotationStratumDim, string>>;
  available: number;
  allocated: number;
  /** The stratum has fewer answers than its share; the others make up the difference. */
  short: boolean;
}

export interface AnnotationRoundPreview {
  available: number;
  size: number;
  strata: AnnotationStratumPreview[];
}

export interface AnnotationProgress {
  annotator_id: number;
  name: string;
  done: number;
  total: number;
}

export interface AnnotationRoundDetail extends AnnotationRoundSummary {
  progress: AnnotationProgress[];
}

/** An Avaliador's note. `grounding` is null when it does not apply (no retrieved context);
 * with `cannot_evaluate`, both scores are null and `reason` says why. */
export interface AnnotationNoteValues {
  correctness: number | null;
  grounding: number | null;
  cannot_evaluate: boolean;
  reason: string | null;
  comment: string | null;
}

/** One answer as an Avaliador sees it: no Técnica, LLM, Experimento or automatic score. */
export interface AnnotationQueueItem {
  id: number;
  position: number;
  question: string;
  question_type: string | null;
  reference_answer: string | null;
  evidence: string[];
  retrieved_context: string[];
  generated_answer: string;
  /** False when the system retrieved no context (e.g. closed_book): Fundamentação does not apply. */
  grounding_applicable: boolean;
  note: AnnotationNoteValues | null;
}

export interface AnnotationQueue {
  round: AnnotationRoundSummary;
  annotator: { id: number; name: string };
  items: AnnotationQueueItem[];
  done: number;
  total: number;
}

export interface AnnotationRoundInput {
  name: string;
  /** Combinações to sample from, as "experiment:run"; a pairwise Rodada takes exactly two. */
  items?: string[];
  experiment_id?: number;
  /** Optional for a pairwise Rodada (every common question goes in); required otherwise. */
  sample_size?: number;
  seed?: number | null;
  description?: string;
  strata?: AnnotationStratumDim[];
  allocation?: "proportional" | "equal";
  pilot?: boolean;
  kind?: AnnotationRoundKind;
}

export interface AgreementValue {
  value: number | null;
  low: number | null;
  high: number | null;
}

export interface AgreementDimension {
  /** Items with at least two scores in this dimension. */
  n: number;
  alpha: AgreementValue;
  /** Only with exactly two Avaliadores. */
  kappa: AgreementValue | null;
  confusion: { avaliadores: string[]; levels: number[]; matrix: number[][] } | null;
}

export interface AnnotationAgreement {
  round: AnnotationRoundSummary;
  avaliadores: string[];
  dimensions: Record<"correctness" | "grounding", AgreementDimension>;
  disagreements: {
    item_id: number; position: number; question: string; generated_answer: string;
    notes: Record<string, AnnotationNoteValues>;
  }[];
  note: string | null;
}

export interface AdjudicationItem {
  id: number;
  position: number;
  question: string;
  reference_answer: string | null;
  evidence: string[];
  retrieved_context: string[];
  generated_answer: string;
  grounding_applicable: boolean;
  /** Every Avaliador's note, by name (the adjudicator sees them only here, on disputed Items). */
  notes: Record<string, AnnotationNoteValues>;
  disputed: ("correctness" | "grounding")[];
  adjudication: { correctness: number | null; grounding: number | null } | null;
}

export interface AdjudicationView {
  round: AnnotationRoundSummary;
  items: AdjudicationItem[];
  decided: number;
  total: number;
}

export interface FinalNotes {
  round: AnnotationRoundSummary;
  items: {
    id: number; position: number;
    final: { correctness: number | null; grounding: number | null };
    status: "concordância" | "adjudicada" | "pendente" | "uma nota" | "sem notas";
  }[];
  pending: number;
}

export interface MetricCorrelation {
  metric: string;
  n: number;
  rho: number | null;
  low: number | null;
  high: number | null;
}

export interface MeanCi {
  mean: number;
  low: number;
  high: number;
}

export interface ValidationGroup {
  n: number;
  human: MeanCi;
  /** Mean answer_correctness of the same Items. */
  automatic: MeanCi | null;
}

export interface AnnotationValidation {
  round: AnnotationRoundSummary;
  pending: number;
  n: number;
  correlations: { correctness: MetricCorrelation[]; grounding: MetricCorrelation[] };
  by_combination: (ValidationGroup & { rag: string; llm: string })[];
  by_question_type: (ValidationGroup & { question_type: string })[];
}

export interface RetestAgreement {
  retest_round_id: number;
  status: "open" | "closed";
  avaliador: string;
  done: number;
  total: number;
  dimensions: Record<"correctness" | "grounding", { n: number; alpha: AgreementValue }>;
}

// ---- Pairwise (side-by-side) comparison Rodadas ----

export type PairwisePreference = "A" | "tie" | "B";

export type PairwiseReason = "mais_correta" | "mais_completa" | "mais_concisa" | "menos_invencao" | "outro";

/** An Avaliador's preference between the two answers of one pairwise Item. `reasons` is
 * empty on a tie; with `cannot_evaluate`, `preference` is null and `reason` says why. */
export interface PairwiseNoteValues {
  preference: PairwisePreference | null;
  reasons: PairwiseReason[];
  cannot_evaluate: boolean;
  reason: string | null;
  comment: string | null;
}

/** One question of a pairwise Rodada as an Avaliador sees it: blind (no Técnica, LLM,
 * Experimento, or which Combinação sits at A or B). */
export interface PairwiseQueueItem {
  id: number;
  position: number;
  question: string;
  question_type: string | null;
  reference_answer: string | null;
  evidence: string[];
  answer_a: string;
  context_a: string[];
  answer_b: string;
  context_b: string[];
  note: PairwiseNoteValues | null;
}

export interface PairwiseQueue {
  round: AnnotationRoundSummary;
  annotator: { id: number; name: string };
  items: PairwiseQueueItem[];
  done: number;
  total: number;
}

export interface PairAdjudicationItem {
  id: number;
  position: number;
  question: string;
  reference_answer: string | null;
  evidence: string[];
  answer_a: string;
  context_a: string[];
  answer_b: string;
  context_b: string[];
  notes: Record<string, PairwiseNoteValues>;
  adjudication: PairwisePreference | null;
}

export interface PairAdjudicationView {
  round: AnnotationRoundSummary;
  items: PairAdjudicationItem[];
  decided: number;
  total: number;
}

export interface PairwiseConfusion {
  avaliadores: string[];
  levels: string[];
  matrix: number[][];
}

export interface PairwiseAgreementDimension {
  n: number;
  alpha: AgreementValue;
  kappa_unweighted: AgreementValue | null;
  kappa_linear: AgreementValue | null;
  confusion: PairwiseConfusion | null;
}

export interface PairwiseAgreement {
  round: AnnotationRoundSummary;
  avaliadores: string[];
  dimension: PairwiseAgreementDimension;
  disagreements: {
    item_id: number; position: number; question: string;
    notes: Record<string, PairwiseNoteValues>;
  }[];
  note: string | null;
}

/** One of a pairwise Rodada's two Combinações, unblinded (shown only in the summary/export). */
export interface PairwiseCombinationRef {
  experiment_id: number;
  run_id: number;
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
}

export interface PairwiseProportion {
  value: number | null;
  low: number | null;
  high: number | null;
}

/** Wins of each side ("1": pair_run_1, "2": pair_run_2), ties, a two-sided sign test
 * p-value over the decided (non-tie) items, each side's win proportion with a 95% Wilson CI,
 * and reason counts among each side's wins. */
export interface PairwiseSideStats {
  wins: Record<"1" | "2", number>;
  ties: number;
  n_decided: number;
  sign_test_p: number | null;
  proportion: Record<"1" | "2", PairwiseProportion>;
  reasons: Record<"1" | "2", Record<string, number>>;
}

export interface PairwiseSummary {
  round: AnnotationRoundSummary;
  pair_run_1: PairwiseCombinationRef;
  pair_run_2: PairwiseCombinationRef;
  avaliadores: Record<string, PairwiseSideStats>;
  final: PairwiseSideStats;
  pending: number;
}
