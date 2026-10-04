export interface LlmOption {
  value: string;
  label: string;
  location: "local" | "remote";
}

export interface IndexPair {
  chunking: string;
  embedding: string;
}

export interface Options {
  bases: string[];
  base_indexes?: Record<string, IndexPair[]>;
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
  created_at: string;
}

export interface ExperimentList {
  items: ExperimentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExperimentResultRow {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
  question: string;
  answer: string;
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
}

export interface ExperimentProgress {
  completed: number;
  total: number;
  /** Staged runs: "generating", then "evaluating" while the answers are scored;
   * "building_graph" while a Grafo de conhecimento is built. */
  phase?: string | null;
  /** Chunks extracted / total of the Grafo being built; null when none is. */
  graph?: { extracted: number; total: number } | null;
}

/** A Grafo de conhecimento the experiment would build: Índice × LLM extrator. */
export interface GraphToBuild {
  chunking: string;
  embedding: string;
  llm: string;
}

export interface ExperimentPreflightInput {
  base: string;
  indexes: IndexPair[];
  rags: string[];
  llms: string[];
}

export interface ExperimentPreflight {
  graphs_to_build: GraphToBuild[];
}

export interface ExperimentDetail {
  id: number;
  name: string;
  status: string;
  created_at?: string;
  finished_at?: string;
  pause_requested?: boolean;
  error?: string | null;
  /** Embedder that scored this experiment's answers (absent on old runs). */
  eval_embedding?: string | null;
  progress?: ExperimentProgress;
  results: ExperimentResultRow[];
  prompts?: Record<string, Record<string, string>>;
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
}

export interface EvaluationSettings {
  /** Embedder that scores experiments that do not name one. */
  eval_embedding: string;
  embeddings: { name: string; local: boolean }[];
  metrics: { name: string; uses_embedding: boolean; requires_reference: boolean }[];
}
