import { describe, expect, it } from "vitest";

import type { ExperimentResultRow } from "../../api/types";
import { MEDIA_KEY, rankByMedia, rankCombinations } from "../../experiments/ranking";
import {
  DEFAULT_FOCUS, type FocusState, costPoints, dimensionEffects, focusSet, hasCost, metricLabel, metricProfile, metricValue, paretoFrontier, quartiles, questionMatrix, rowValue,
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

describe("dimensionEffects", () => {
  it("orders dimensions by effect size and options by mean", () => {
    const eff = dimensionEffects(fixture(), MEDIA_KEY);
    // chunking: token 0.65 vs recursive 0.25; rag: 0.2; llm: 0.1
    expect(eff.varying.map((d) => d.dim)).toEqual(["chunking", "rag", "llm"]);
    expect(eff.varying[0].effect).toBeCloseTo(0.4);
    expect(eff.varying[0].options.map((o) => o.option)).toEqual(["token", "recursive"]);
    const token = eff.varying[0].options[0];
    expect(token.combos).toBe(4);
    expect(token.min).toBeCloseTo(0.5);
    expect(token.max).toBeCloseTo(0.8);
    expect(token.mean).toBeCloseTo(0.65);
  });

  it("lists fixed dimensions and flags an incomplete grid", () => {
    const full = dimensionEffects(fixture(), MEDIA_KEY);
    expect(full.fixed).toEqual([
      { dim: "embedding", option: "e5" },
      { dim: "retriever", option: "similarity" },
    ]);
    expect(full.pending).toEqual([]);
    expect(full.incompleteGrid).toBe(false);
    const missing = fixture().filter((r) => !(r.chunking === "recursive" && r.rag === "naive" && r.llm === "qwen"));
    expect(dimensionEffects(missing, MEDIA_KEY).incompleteGrid).toBe(true);
  });

  it("marks a dimension pending when fewer than 2 of its options have scored combinations", () => {
    // zero out every combination on the "recursive" side: chunking still has 2 raw values,
    // but only "token" ends up with a scored option.
    const results = fixture().map((r) => (r.chunking === "recursive" ? { ...r, scores: {} } : r));
    const eff = dimensionEffects(results, MEDIA_KEY);
    expect(eff.pending).toEqual(["chunking"]);
    expect(eff.varying.map((d) => d.dim)).toEqual(["rag", "llm"]);
  });
});

describe("cost", () => {
  it("averages cost and quality per combination, skipping combos without either", () => {
    const results = fixture();
    results[0] = { ...results[0], scores: {} };
    results[1] = { ...results[1], scores: {} };   // combination i = 0 has no metric at all
    const points = costPoints(results, "latency", MEDIA_KEY);
    expect(points).toHaveLength(7);
    expect(points.every((p) => Number.isFinite(p.cost) && Number.isFinite(p.quality))).toBe(true);
  });

  it("hasCost is false when every row is 0", () => {
    const zero = fixture().map((r) => ({ ...r, latency_ms: 0 }));
    expect(hasCost(zero, "latency")).toBe(false);
    expect(hasCost(zero, "tokens")).toBe(true);
    expect(costPoints(zero, "latency", MEDIA_KEY)).toEqual([]);
  });

  it("paretoFrontier keeps non-dominated points, sorted by cost", () => {
    const frontier = paretoFrontier(costPoints(fixture(), "latency", MEDIA_KEY));
    expect(frontier.map((p) => p.cost)).toEqual([100, 200, 300, 600]);
  });

  it("paretoFrontier keeps exact ties", () => {
    const a = { cost: 1, quality: 0.5 };
    const b = { cost: 1, quality: 0.5 };
    expect(paretoFrontier([a, b, { cost: 2, quality: 0.4 }])).toEqual([a, b]);
  });
});

describe("quartiles", () => {
  it("interpolates like R-7", () => {
    expect(quartiles([4, 1, 3, 2])).toEqual({ q1: 1.75, median: 2.5, q3: 3.25 });
    expect(quartiles([1, 2, 3])).toEqual({ q1: 1.5, median: 2, q3: 2.5 });
    expect(quartiles([5])).toEqual({ q1: 5, median: 5, q3: 5 });
    expect(quartiles([])).toBeNull();
  });
});

describe("questionMatrix", () => {
  it("orders questions hardest first, cells aligned with the focus", () => {
    const results = fixture();
    const focused = focusSet(ranked(results), { ...DEFAULT_FOCUS, n: 1 }); // #1, #8
    const m = questionMatrix(results, focused, "faithfulness");
    expect(m.map((r) => r.question)).toEqual(["Pergunta difícil", "Pergunta fácil"]);
    expect(m[0].cells.map((c) => c.value)).toEqual([0.7, 0]);
    expect(m[0].cells[0].row?.llm).toBe("gemma");
  });

  it("leaves a null cell for a missing answer and puts all-null questions last", () => {
    const results = fixture().filter((r) => !(r.llm === "gemma" && r.chunking === "token" && r.rag === "agentic" && r.question === "Pergunta fácil"));
    results.push({ ...results[0], question: "Sem métricas", scores: {} });
    const focused = focusSet(ranked(results), { ...DEFAULT_FOCUS, n: 1 });
    const m = questionMatrix(results, focused, MEDIA_KEY);
    expect(m[m.length - 1].question).toBe("Sem métricas");
    const easy = m.find((r) => r.question === "Pergunta fácil")!;
    expect(easy.cells[0]).toEqual({ value: null, row: null });
  });
});
