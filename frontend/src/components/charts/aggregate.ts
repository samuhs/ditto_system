/** Pure data shaping for the charts tab: focus set and one function per figure. */
import type { ExperimentResultRow } from "../../api/types";
import { MEDIA_KEY, type RankRow, groupByCombo, mean, rowMedia } from "../../experiments/ranking";
import { term } from "../../glossary";

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
