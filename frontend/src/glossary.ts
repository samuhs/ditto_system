/**
 * Plain-language names and one-line explanations for every technique and
 * metric the backend registers. Techniques are plugins, so anything missing
 * here falls back to its registry key with no description.
 */
export interface Term {
  name: string;
  description?: string;
}

type Dimension = "chunking" | "embedding" | "rag" | "retriever" | "metric";

const TERMS: Record<Dimension, Record<string, Term>> = {
  chunking: {
    fixed: {
      name: "Tamanho fixo",
      description: "Corta o texto em blocos do mesmo tamanho, sem olhar a estrutura.",
    },
    recursive: {
      name: "Recursivo",
      description: "Corta por parágrafo, depois por frase, até caber no tamanho. Preserva a estrutura.",
    },
    token: {
      name: "Por tokens",
      description: "Blocos medidos em tokens do modelo, não em caracteres.",
    },
    semantic: {
      name: "Semântico",
      description: "Junta frases vizinhas enquanto o assunto é o mesmo e corta quando ele muda.",
    },
  },
  embedding: {
    gemini: {
      name: "Gemini",
      description: "Modelo do Google, via API. Precisa da chave do Gemini.",
    },
    e5: {
      name: "E5",
      description: "Modelo multilíngue que roda na sua máquina, sem API.",
    },
    paraphrase: {
      name: "Paraphrase",
      description: "Modelo local e leve, bom para frases com o mesmo sentido.",
    },
  },
  rag: {
    naive: {
      name: "Simples",
      description: "Busca os trechos uma vez e responde com eles.",
    },
    agentic: {
      name: "Agêntico",
      description: "O modelo decide se precisa buscar de novo antes de responder.",
    },
    hyde: {
      name: "HyDE",
      description: "Escreve uma resposta hipotética e usa ela para buscar os trechos.",
    },
    rerank: {
      name: "Reordenação",
      description: "Busca mais trechos e reordena por relevância antes de responder.",
    },
    crag: {
      name: "Corretivo (CRAG)",
      description: "Avalia os trechos achados e refaz a busca quando eles são fracos.",
    },
    compression: {
      name: "Compressão",
      description: "Reduz cada trecho ao que interessa à pergunta antes de responder.",
    },
  },
  retriever: {
    similarity: {
      name: "Similaridade",
      description: "Os trechos mais parecidos com a pergunta.",
    },
    mmr: {
      name: "Diversidade (MMR)",
      description: "Parecidos com a pergunta, mas diferentes entre si.",
    },
    multi_query: {
      name: "Múltiplas consultas",
      description: "Reescreve a pergunta de vários jeitos e junta os resultados.",
    },
    parent_document: {
      name: "Documento pai",
      description: "Acha o trecho e devolve o bloco maior onde ele está.",
    },
  },
  metric: {
    answer_relevancy: {
      name: "Relevância",
      description: "A resposta trata do que foi perguntado?",
    },
    faithfulness: {
      name: "Fidelidade",
      description: "A resposta se apoia só nos trechos recuperados, sem inventar?",
    },
    context_precision: {
      name: "Precisão do contexto",
      description: "Os trechos recuperados são úteis para a pergunta?",
    },
    context_recall: {
      name: "Cobertura do contexto",
      description: "Os trechos cobrem o que a resposta de referência precisa?",
    },
    answer_correctness: {
      name: "Correção",
      description: "A resposta concorda com a resposta de referência?",
    },
    rouge_l: {
      name: "ROUGE-L",
      description: "Quanto do texto coincide com a resposta de referência.",
    },
  },
};

export function term(dimension: Dimension, key: string): Term {
  return TERMS[dimension][key] ?? { name: key };
}

/** Name of a prompt-owning technique, which may be a RAG technique or a retriever. */
export function techniqueName(key: string): string {
  return TERMS.rag[key]?.name ?? TERMS.retriever[key]?.name ?? key;
}

export const DIMENSION_LABEL: Record<Exclude<Dimension, "metric">, string> = {
  chunking: "Corte",
  embedding: "Embedding",
  rag: "Técnica de RAG",
  retriever: "Busca",
};

export type StatusTone = "done" | "running" | "paused" | "failed" | "idle";

const STATUS: Record<string, { label: string; tone: StatusTone }> = {
  done: { label: "Concluído", tone: "done" },
  running: { label: "Em andamento", tone: "running" },
  pending: { label: "Na fila", tone: "running" },
  paused: { label: "Pausado", tone: "paused" },
  failed: { label: "Falhou", tone: "failed" },
};

export function statusInfo(status: string): { label: string; tone: StatusTone } {
  return STATUS[status] ?? { label: status, tone: "idle" };
}
