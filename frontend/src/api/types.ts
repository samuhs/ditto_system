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
}

export interface ExperimentDetail {
  id: number;
  name: string;
  status: string;
  created_at?: string;
  finished_at?: string;
  pause_requested?: boolean;
  error?: string | null;
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

export interface AppSettings {
  gemini_api_key_set: boolean;
  ollama_models: OllamaModel[];
}
