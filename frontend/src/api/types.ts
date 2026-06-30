export interface Options {
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

export interface ExperimentDetail {
  id: number;
  name: string;
  status: string;
  results: ExperimentResultRow[];
}
