/** Pure data shaping for the charts tab: focus set and one function per figure. */
import { quantileSorted } from "d3-array";

import type { ExperimentResultRow } from "../../api/types";
import {
  DIMS, type Dim, MEDIA_KEY, type RankRow, comboKey, groupByCombo, mean, rowMedia,
} from "../../experiments/ranking";
import { DIMENSION_LABEL, term } from "../../glossary";
import type { Combination } from "../Score";

export type FocusMode = "top_bottom" | "top" | "all";

export interface FocusState {
  mode: FocusMode;
  n: number;
  /** MEDIA_KEY or a metric key: the quality axis of figures 2–4. */
  metric: string;
  /** comboKeys picked by hand. */
  manual: string[];
}

export const DEFAULT_FOCUS: FocusState = { mode: "top_bottom", n: 3, metric: MEDIA_KEY, manual: [] };

export type Group = "top" | "bottom" | "manual";

export interface FocusedCombo {
  row: RankRow;
  /** 1-based place in the ranking by média. */
  place: number;
  group: Group;
}

export function metricLabel(metric: string): string {
  return metric === MEDIA_KEY ? "Média" : term("metric", metric).name;
}

/** One row's value for a metric id (MEDIA_KEY = mean of its metrics); null when missing. */
export function rowValue(row: ExperimentResultRow, metric: string): number | null {
  if (metric === MEDIA_KEY) return rowMedia(row);
  return metric in row.scores ? row.scores[metric] : null;
}

export interface MetricValue {
  value: number | null;
  /** Rows that have the metric. */
  n: number;
  total: number;
}

export function metricValue(rows: ExperimentResultRow[], metric: string): MetricValue {
  const values = rows.map((r) => rowValue(r, metric)).filter((v): v is number => v !== null);
  return { value: mean(values), n: values.length, total: rows.length };
}

/** The combinations in focus, in ranking order. `ranked` must be sorted by média desc. */
export function focusSet(ranked: RankRow[], focus: FocusState): FocusedCombo[] {
  const n = Math.max(1, Math.min(10, Math.round(focus.n)));
  const groups = new Map<string, Group>();
  if (focus.mode === "all") {
    ranked.forEach((r) => groups.set(r.key, "top"));
  } else {
    ranked.slice(0, n).forEach((r) => groups.set(r.key, "top"));
    if (focus.mode === "top_bottom") {
      ranked.slice(-n).forEach((r) => {
        if (!groups.has(r.key)) groups.set(r.key, "bottom");
      });
    }
  }
  for (const key of focus.manual) if (!groups.has(key)) groups.set(key, "manual");
  // Iterating `ranked` drops manual keys that no longer exist.
  return ranked.flatMap((row, i) => {
    const group = groups.get(row.key);
    return group ? [{ row, place: i + 1, group }] : [];
  });
}

export interface ProfilePoint extends MetricValue {
  combo: FocusedCombo;
}

export interface ProfileLine {
  metric: string;
  points: ProfilePoint[];
  topMean: number | null;
  bottomMean: number | null;
  /** bottomMean − topMean; null without both groups. */
  gap: number | null;
}

/** Figure 1: one line per metric (média last), ordered by the largest top/bottom gap. */
export function metricProfile(
  results: ExperimentResultRow[],
  focused: FocusedCombo[],
  metricKeys: string[],
): ProfileLine[] {
  const byKey = groupByCombo(results);
  const line = (metric: string): ProfileLine => {
    const points = focused.map((combo) => ({ combo, ...metricValue(byKey.get(combo.row.key) ?? [], metric) }));
    const groupMean = (g: Group) =>
      mean(points.filter((p) => p.combo.group === g && p.value !== null).map((p) => p.value as number));
    const topMean = groupMean("top");
    const bottomMean = groupMean("bottom");
    const gap = topMean !== null && bottomMean !== null ? bottomMean - topMean : null;
    return { metric, points, topMean, bottomMean, gap };
  };
  const size = (l: ProfileLine) => (l.gap === null ? -1 : Math.abs(l.gap));
  const lines = metricKeys.map(line).sort((a, b) => size(b) - size(a));
  return [...lines, line(MEDIA_KEY)];
}

export const DIM_LABEL: Record<Dim, string> = { ...DIMENSION_LABEL, llm: "Modelo (LLM)" };

export interface OptionEffect {
  option: string;
  mean: number;
  min: number;
  max: number;
  /** Combinations with this option that have the metric. */
  combos: number;
}

export interface DimensionEffect {
  dim: Dim;
  /** Best option first. */
  options: OptionEffect[];
  /** Best option's mean minus the worst's. */
  effect: number;
}

export interface DimensionEffects {
  /** Largest effect first. */
  varying: DimensionEffect[];
  fixed: { dim: Dim; option: string }[];
  /** Dimensions with 2+ options in the grid, but fewer than 2 of them have any scored combination. */
  pending: Dim[];
  /** Fewer combinations than the product of every dimension's options. */
  incompleteGrid: boolean;
}

/** Figure 2: marginal effect of each dimension over every combination. */
export function dimensionEffects(results: ExperimentResultRow[], metric: string): DimensionEffects {
  const combos = [...groupByCombo(results).values()].map((rows) => ({
    combo: rows[0],
    value: metricValue(rows, metric).value,
  }));
  const varying: DimensionEffect[] = [];
  const fixed: { dim: Dim; option: string }[] = [];
  const pending: Dim[] = [];
  let gridSize = 1;
  for (const dim of DIMS) {
    const all = [...new Set(combos.map((c) => c.combo[dim]))].sort();
    gridSize *= all.length;
    if (all.length === 1) fixed.push({ dim, option: all[0] });
    if (all.length < 2) continue;
    const options = all
      .flatMap((option) => {
        const values = combos
          .filter((c) => c.combo[dim] === option && c.value !== null)
          .map((c) => c.value as number);
        if (values.length === 0) return [];
        return [{ option, mean: mean(values) as number, min: Math.min(...values), max: Math.max(...values), combos: values.length }];
      })
      .sort((a, b) => b.mean - a.mean);
    if (options.length < 2) {
      pending.push(dim);
      continue;
    }
    varying.push({ dim, options, effect: options[0].mean - options[options.length - 1].mean });
  }
  varying.sort((a, b) => b.effect - a.effect);
  return { varying, fixed, pending, incompleteGrid: combos.length < gridSize };
}

export type CostKind = "latency" | "tokens";

export const COST_LABEL: Record<CostKind, string> = {
  latency: "Latência média (ms)",
  tokens: "Tokens médios",
};

function costOf(row: ExperimentResultRow, cost: CostKind): number {
  return cost === "latency" ? row.latency_ms : row.tokens;
}

export function hasCost(results: ExperimentResultRow[], cost: CostKind): boolean {
  return results.some((r) => costOf(r, cost) > 0);
}

export interface CostPoint {
  key: string;
  combo: Combination;
  cost: number;
  quality: number;
}

/** Figure 3: mean cost (rows > 0) and quality per combination; combos missing either are left out. */
export function costPoints(results: ExperimentResultRow[], cost: CostKind, metric: string): CostPoint[] {
  return [...groupByCombo(results).entries()].flatMap(([key, rows]) => {
    const c = mean(rows.map((r) => costOf(r, cost)).filter((v) => v > 0));
    const q = metricValue(rows, metric).value;
    return c === null || q === null ? [] : [{ key, combo: rows[0], cost: c, quality: q }];
  });
}

/** Points no other point beats on both cost (≤) and quality (≥), one of them strictly. */
export function paretoFrontier<T extends { cost: number; quality: number }>(points: T[]): T[] {
  const dominated = (p: T) =>
    points.some(
      (q) => q !== p && q.cost <= p.cost && q.quality >= p.quality && (q.cost < p.cost || q.quality > p.quality),
    );
  return points.filter((p) => !dominated(p)).sort((a, b) => a.cost - b.cost || b.quality - a.quality);
}

export function quartiles(values: number[]): { q1: number; median: number; q3: number } | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  return {
    q1: quantileSorted(s, 0.25) as number,
    median: quantileSorted(s, 0.5) as number,
    q3: quantileSorted(s, 0.75) as number,
  };
}

export interface MatrixCell {
  value: number | null;
  row: ExperimentResultRow | null;
}

export interface MatrixRow {
  question: string;
  /** Mean over the focused combinations; lower is harder. */
  difficulty: number | null;
  /** Aligned with `focused`. */
  cells: MatrixCell[];
}

/** Figure 4: question × focused combination, hardest question first, no-data questions last. */
export function questionMatrix(
  results: ExperimentResultRow[],
  focused: FocusedCombo[],
  metric: string,
): MatrixRow[] {
  const keys = focused.map((f) => f.row.key);
  const byQuestion = new Map<string, Map<string, ExperimentResultRow>>();
  for (const r of results) {
    const k = comboKey(r);
    if (!keys.includes(k)) continue;
    const cells = byQuestion.get(r.question) ?? new Map<string, ExperimentResultRow>();
    if (!cells.has(k)) cells.set(k, r);
    byQuestion.set(r.question, cells);
  }
  const rows = [...byQuestion.entries()].map(([question, byKey]) => {
    const cells = keys.map((k) => {
      const row = byKey.get(k) ?? null;
      return { row, value: row ? rowValue(row, metric) : null };
    });
    const difficulty = mean(cells.flatMap((c) => (c.value === null ? [] : [c.value])));
    return { question, difficulty, cells };
  });
  return rows.sort((a, b) => {
    if (a.difficulty === null || b.difficulty === null) {
      return (a.difficulty === null ? 1 : 0) - (b.difficulty === null ? 1 : 0);
    }
    return a.difficulty - b.difficulty;
  });
}
