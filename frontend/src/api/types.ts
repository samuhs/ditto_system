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
  llms: string[];
  llm_options?: LlmOption[];
  rags: string[];
  retrievers: string[];
  metrics: string[];
}

export interface IngestResult {
  collections: string[];
  total_chunks: number;
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
}

export interface ExperimentProgress {
  completed: number;
  total: number;
  /** Staged runs: "generating", then "evaluating" while the answers are scored. */
  phase?: string | null;
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
  /** Share of retrievals that brought the annotated evidence back; null without evidence. */
  hit_rate: number | null;
  with_evidence: Record<string, number>;
  without_evidence: Record<string, number>;
}

export interface QuestionDifficulty {
  question: string;
  signals: Record<string, number>;
  retrieval_signals: Record<string, number>;
  by_llm: Record<string, DifficultyCell>;
}

export interface ExperimentDifficulty {
  llms: string[];
  metrics: string[];
  questions: QuestionDifficulty[];
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

export interface OllamaModel {
  id: string;
  model: string;
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
  ollama_models: OllamaModel[];
}

export interface EvaluationSettings {
  /** Embedder that scores experiments that do not name one. */
  eval_embedding: string;
  embeddings: { name: string; local: boolean }[];
  metrics: { name: string; uses_embedding: boolean; requires_reference: boolean }[];
}
