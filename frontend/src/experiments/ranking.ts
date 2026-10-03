/** Ranking of an experiment's combinations, shared by the ranking table and the charts. */
import type { ExperimentResultRow, GraphStats } from "../api/types";
import type { Combination } from "../components/Score";
import { term } from "../glossary";
import { ofType, typesIn } from "./questionTypes";

/** Sort key and metric id for the plain mean of every metric. */
export const MEDIA_KEY = "__media__";

export type Dim = keyof Combination;
export const DIMS: Dim[] = ["chunking", "embedding", "rag", "retriever", "llm"];

export function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function rowMedia(row: ExperimentResultRow): number | null {
  return mean(Object.values(row.scores));
}

export function comboKey(c: Combination): string {
  return DIMS.map((d) => c[d]).join("|");
}

export function dimName(dim: Dim, key: string): string {
  return dim === "llm" ? key : term(dim, key).name;
}

export function comboText(c: Combination): string {
  return DIMS.map((d) => dimName(d, c[d])).join(" · ");
}

export function groupByCombo(results: ExperimentResultRow[]): Map<string, ExperimentResultRow[]> {
  const groups = new Map<string, ExperimentResultRow[]>();
  for (const r of results) {
    const k = comboKey(r);
    const rows = groups.get(k);
    if (rows) rows.push(r);
    else groups.set(k, [r]);
  }
  return groups;
}

export interface RankRow {
  key: string;
  combo: Combination;
  count: number;
  scores: Record<string, number | null>;
  /** GraphRAG combinations: stats of the Grafo de conhecimento they used. */
  graphStats: GraphStats | null;
  media: number | null;
  /** Média over the questions of each Tipo de pergunta the combination answered. */
  mediaByType: Record<string, number | null>;
}

function metricMeans(rows: ExperimentResultRow[], metricKeys: string[]): Record<string, number | null> {
  const scores: Record<string, number | null> = {};
  for (const m of metricKeys) {
    scores[m] = mean(rows.filter((r) => m in r.scores).map((r) => r.scores[m]));
  }
  return scores;
}

function mediaOf(rows: ExperimentResultRow[]): number | null {
  return mean(rows.map(rowMedia).filter((v): v is number => v !== null));
}

export function rankCombinations(results: ExperimentResultRow[], metricKeys: string[]): RankRow[] {
  return [...groupByCombo(results).entries()].map(([key, rows]) => ({
    key,
    combo: rows[0],
    count: rows.length,
    scores: metricMeans(rows, metricKeys),
    media: mediaOf(rows),
    mediaByType: Object.fromEntries(typesIn(rows).map((t) => [t, mediaOf(ofType(rows, t))])),
    graphStats: rows[0].graph_stats ?? null,
  }));
}

export interface TypeSummary {
  type: string;
  /** Distinct questions of this type. */
  questions: number;
  scores: Record<string, number | null>;
  media: number | null;
}

/** Mean of each metric per Tipo de pergunta, over every answer of every combination. */
export function meansByType(results: ExperimentResultRow[], metricKeys: string[]): TypeSummary[] {
  return typesIn(results).map((type) => {
    const rows = ofType(results, type);
    return {
      type,
      questions: new Set(rows.map((r) => r.question)).size,
      scores: metricMeans(rows, metricKeys),
      media: mediaOf(rows),
    };
  });
}

export function rankByMedia(ranking: RankRow[]): RankRow[] {
  return [...ranking].sort((a, b) => (b.media ?? -1) - (a.media ?? -1));
}
