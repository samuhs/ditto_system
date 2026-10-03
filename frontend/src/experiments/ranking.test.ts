import { describe, expect, it } from "vitest";

import type { ExperimentResultRow } from "../api/types";
import {
  comboKey, comboText, groupByCombo, mean, meansByType, rankByMedia, rankCombinations, rowMedia,
} from "./ranking";

function row(over: Partial<ExperimentResultRow>): ExperimentResultRow {
  return {
    chunking: "recursive", embedding: "e5", rag: "naive", retriever: "similarity", llm: "qwen",
    question: "Q", answer: "A", scores: {}, latency_ms: 100, tokens: 10,
    ...over,
  };
}

describe("ranking", () => {
  it("mean is null for an empty list", () => {
    expect(mean([])).toBeNull();
    expect(mean([0.2, 0.4])).toBeCloseTo(0.3);
  });

  it("rowMedia averages the row's metrics", () => {
    expect(rowMedia(row({ scores: { a: 0.2, b: 0.6 } }))).toBeCloseTo(0.4);
    expect(rowMedia(row({ scores: {} }))).toBeNull();
  });

  it("comboKey joins the five dimensions", () => {
    expect(comboKey(row({}))).toBe("recursive|e5|naive|similarity|qwen");
  });

  it("comboText names each dimension with its glossary label", () => {
    expect(comboText(row({ chunking: "token" }))).toContain("Por tokens");
    expect(comboText(row({}))).toContain("qwen");
  });

  it("groups rows by combination and averages each metric", () => {
    const results = [
      row({ question: "Q1", scores: { a: 0.2, b: 0.4 } }),
      row({ question: "Q2", scores: { a: 0.6 } }),
      row({ llm: "gemma", scores: { a: 0.9, b: 0.9 } }),
    ];
    expect(groupByCombo(results).size).toBe(2);
    const ranking = rankCombinations(results, ["a", "b"]);
    const qwen = ranking.find((r) => r.combo.llm === "qwen")!;
    expect(qwen.count).toBe(2);
    expect(qwen.scores.a).toBeCloseTo(0.4);
    expect(qwen.scores.b).toBeCloseTo(0.4);   // only Q1 has b
    expect(qwen.media).toBeCloseTo((0.3 + 0.6) / 2);
  });

  it("rankByMedia sorts by média desc with null last, without mutating", () => {
    const results = [
      row({ llm: "low", scores: { a: 0.1 } }),
      row({ llm: "none", scores: {} }),
      row({ llm: "high", scores: { a: 0.9 } }),
    ];
    const ranking = rankCombinations(results, ["a"]);
    const before = ranking.map((r) => r.combo.llm);
    expect(rankByMedia(ranking).map((r) => r.combo.llm)).toEqual(["high", "low", "none"]);
    expect(ranking.map((r) => r.combo.llm)).toEqual(before);
  });
});

describe("means per Tipo de pergunta", () => {
  const results = [
    row({ question: "S1", scores: { a: 0.8, b: 0.6 } }),
    row({ question: "P1", question_type: "ponte", scores: { a: 0.2, b: 0.4 } }),
    row({ question: "P2", question_type: "ponte", scores: { a: 0.4 } }),
    row({ llm: "gemma", question: "P1", question_type: "ponte", scores: { a: 0.6, b: 0.6 } }),
  ];

  it("gives each combination its média per type, unannotated rows being simples", () => {
    const ranking = rankCombinations(results, ["a", "b"]);
    const qwen = ranking.find((r) => r.combo.llm === "qwen")!;
    expect(qwen.mediaByType.simples).toBeCloseTo(0.7);
    expect(qwen.mediaByType.ponte).toBeCloseTo((0.3 + 0.4) / 2);
    const gemma = ranking.find((r) => r.combo.llm === "gemma")!;
    expect(gemma.mediaByType).toEqual({ ponte: 0.6 });
  });

  it("averages each metric per type over every combination, in glossary order", () => {
    const summary = meansByType(results, ["a", "b"]);
    expect(summary.map((s) => s.type)).toEqual(["simples", "ponte"]);
    const ponte = summary[1];
    expect(ponte.questions).toBe(2);
    expect(ponte.scores.a).toBeCloseTo((0.2 + 0.4 + 0.6) / 3);
    expect(ponte.scores.b).toBeCloseTo(0.5);
    expect(ponte.media).toBeCloseTo((0.3 + 0.4 + 0.6) / 3);
  });
});
