/**
 * Synthetic results for chart tests: a full 2 × 2 × 2 grid (chunking × rag × llm),
 * two questions each. Combination i (0..7) has média 0.1 + 0.1·i, so its ranking
 * place is 8 − i: i = 7 (token · agentic · gemma) is #1, i = 0 is #8.
 * "Pergunta difícil" scores 0.1 below "Pergunta fácil" on faithfulness.
 * Latency is 100 × [1,4,7,2,5,8,3,6][i] ms, so the Pareto frontier is i = 0, 3, 6, 7
 * (places #8, #5, #2, #1). Tokens follow the same pattern × 10.
 */
import type { ExperimentResultRow } from "../../api/types";

const COST = [1, 4, 7, 2, 5, 8, 3, 6];

export function fixture(): ExperimentResultRow[] {
  const rows: ExperimentResultRow[] = [];
  let i = 0;
  for (const chunking of ["recursive", "token"]) {
    for (const rag of ["naive", "agentic"]) {
      for (const llm of ["qwen", "gemma"]) {
        const base = Math.round((0.1 + i * 0.1) * 100) / 100;
        for (const [question, delta] of [["Pergunta fácil", 0.1], ["Pergunta difícil", -0.1]] as const) {
          rows.push({
            chunking, embedding: "e5", rag, retriever: "similarity", llm,
            question,
            answer: `Resposta ${i} para ${question}`,
            // faithfulness averages to base across the two questions; média per combo = base
            scores: { faithfulness: Math.round((base + delta) * 100) / 100, answer_relevancy: base },
            latency_ms: 100 * COST[i],
            tokens: 10 * COST[i],
          });
        }
        i++;
      }
    }
  }
  return rows;
}
