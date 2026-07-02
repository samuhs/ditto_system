export interface Options {
  bases: string[];
  chunkings: string[];
  embeddings: string[];
  llms: string[];
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
}

export interface ExperimentResultRow {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
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
