import { describe, expect, it } from "vitest";

import type { ExperimentResultRow } from "../../api/types";
import { MEDIA_KEY, rankByMedia, rankCombinations } from "../../experiments/ranking";
import {
  DEFAULT_FOCUS, type FocusState, focusSet, metricLabel, metricProfile, metricValue, rowValue,
} from "./aggregate";
import { fixture } from "./testFixture";

const KEYS = ["answer_relevancy", "faithfulness"];
const ranked = (results = fixture()) => rankByMedia(rankCombinations(results, KEYS));
const places = (focus: FocusState, results = fixture()) =>
  focusSet(ranked(results), focus).map((f) => [f.place, f.group]);

describe("metric values", () => {
  it("labels média and glossary metrics", () => {
    expect(metricLabel(MEDIA_KEY)).toBe("Média");
    expect(metricLabel("faithfulness")).toBe("Fidelidade");
  });

  it("rowValue reads a metric or the row's média, null when missing", () => {
    const row = fixture()[0];
    expect(rowValue(row, "answer_relevancy")).toBeCloseTo(0.1);
    expect(rowValue(row, "context_recall")).toBeNull();
    expect(rowValue({ ...row, scores: {} }, MEDIA_KEY)).toBeNull();
  });

  it("metricValue averages only rows that have the metric and reports n", () => {
    const [a, b] = fixture();
    const partial: ExperimentResultRow = { ...b, scores: { answer_relevancy: 0.5 } };
    expect(metricValue([a, partial], "faithfulness")).toEqual({ value: a.scores.faithfulness, n: 1, total: 2 });
    expect(metricValue([], MEDIA_KEY)).toEqual({ value: null, n: 0, total: 0 });
  });
});

describe("focusSet", () => {
  it("defaults to top 3 and bottom 3, ordered by place", () => {
    expect(places(DEFAULT_FOCUS)).toEqual([
      [1, "top"], [2, "top"], [3, "top"], [6, "bottom"], [7, "bottom"], [8, "bottom"],
    ]);
  });

  it("keeps an overlapping combination in top when there are fewer than 2N", () => {
    const five = fixture().filter((r) => !(r.chunking === "recursive" && r.rag === "naive")); // drop #7, #8
    // 6 combinations, N = 4: top = #1..#4, bottom = last 4 minus top = #5, #6
    expect(places({ ...DEFAULT_FOCUS, n: 4 }, five)).toEqual([
      [1, "top"], [2, "top"], [3, "top"], [4, "top"], [5, "bottom"], [6, "bottom"],
    ]);
  });

  it("top only and all", () => {
    expect(places({ ...DEFAULT_FOCUS, mode: "top", n: 2 })).toEqual([[1, "top"], [2, "top"]]);
    expect(places({ ...DEFAULT_FOCUS, mode: "all" })).toHaveLength(8);
  });

  it("adds manual picks once and ignores keys that no longer exist", () => {
    const r = ranked();
    const focus = { ...DEFAULT_FOCUS, n: 1, manual: [r[3].key, r[0].key, "gone|x|y|z|w"] };
    expect(places(focus)).toEqual([[1, "top"], [4, "manual"], [8, "bottom"]]);
  });

  it("clamps N to 1..10", () => {
    expect(places({ ...DEFAULT_FOCUS, mode: "top", n: 0 })).toEqual([[1, "top"]]);
    expect(places({ ...DEFAULT_FOCUS, mode: "top", n: 99 })).toHaveLength(8);
  });
});

describe("metricProfile", () => {
  it("computes the gap bottom − top, média last", () => {
    const results = fixture();
    const focused = focusSet(ranked(results), { ...DEFAULT_FOCUS, n: 1 }); // #1 (0.8) vs #8 (0.1)
    const lines = metricProfile(results, focused, KEYS);
    expect(lines).toHaveLength(3);
    expect(lines[2].metric).toBe(MEDIA_KEY);
    const media = lines[2];
    expect(media.topMean).toBeCloseTo(0.8);
    expect(media.bottomMean).toBeCloseTo(0.1);
    expect(media.gap).toBeCloseTo(-0.7);
    expect(media.points.map((p) => p.combo.place)).toEqual([1, 8]);
  });

  it("orders by the largest absolute gap", () => {
    const results = fixture().map((r) =>
      // make faithfulness equal everywhere: its gap becomes 0
      ({ ...r, scores: { ...r.scores, faithfulness: 0.5 } }),
    );
    const focused = focusSet(ranked(results), { ...DEFAULT_FOCUS, n: 1 });
    expect(metricProfile(results, focused, KEYS).map((l) => l.metric)).toEqual([
      "answer_relevancy", "faithfulness", MEDIA_KEY,
    ]);
    expect(metricProfile(results, focused, KEYS)[1].gap).toBeCloseTo(0);
  });

  it("has no gap without a bottom group", () => {
    const results = fixture();
    const focused = focusSet(ranked(results), { ...DEFAULT_FOCUS, mode: "top" });
    const lines = metricProfile(results, focused, KEYS);
    expect(lines.every((l) => l.gap === null && l.bottomMean === null)).toBe(true);
  });
});
