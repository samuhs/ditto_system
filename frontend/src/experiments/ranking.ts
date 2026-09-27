/** Ranking of an experiment's combinations, shared by the ranking table and the charts. */
import type { ExperimentResultRow } from "../api/types";
import type { Combination } from "../components/Score";
import { term } from "../glossary";

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
  media: number | null;
}

export function rankCombinations(results: ExperimentResultRow[], metricKeys: string[]): RankRow[] {
  return [...groupByCombo(results).entries()].map(([key, rows]) => {
    const scores: Record<string, number | null> = {};
    for (const m of metricKeys) {
      scores[m] = mean(rows.filter((r) => m in r.scores).map((r) => r.scores[m]));
    }
    return {
      key,
      combo: rows[0],
      count: rows.length,
      scores,
      media: mean(rows.map(rowMedia).filter((v): v is number => v !== null)),
    };
  });
}

export function rankByMedia(ranking: RankRow[]): RankRow[] {
  return [...ranking].sort((a, b) => (b.media ?? -1) - (a.media ?? -1));
}
