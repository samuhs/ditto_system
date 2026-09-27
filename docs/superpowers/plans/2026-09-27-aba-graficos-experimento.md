# Aba "Gráficos" no detalhe do experimento: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** adicionar ao detalhe do experimento uma aba "Gráficos" com quatro figuras (perfil top × bottom, efeito por dimensão, custo × qualidade, estabilidade por pergunta) e uma barra de foco que limita o que aparece.

**Architecture:** tudo no frontend, a partir do `detail.results` que a página já carrega. O cálculo fica em funções puras (`experiments/ranking.ts` e `components/charts/aggregate.ts`), testadas isoladamente. As figuras são componentes React que desenham SVG à mão, com escalas do `d3-scale`. O estado do foco mora em `ExperimentDetailPage`, para sobreviver à troca de abas.

**Tech Stack:** React 18 + TypeScript, Mantine 7, `d3-scale` + `d3-array`, vitest + Testing Library (jsdom).

**Spec:** `docs/superpowers/specs/2026-09-27-aba-graficos-experimento-design.md`

## Global Constraints

- Nenhuma mudança no backend nem na API. Os dados vêm de `ExperimentDetail.results`.
- Dependências novas: só `d3-scale` e `d3-array` (runtime) e `@types/d3-scale` e `@types/d3-array` (dev). Nenhuma biblioteca que desenhe gráficos.
- Identificadores, comentários e erros em **inglês**; textos de UI em **PT-BR**.
- Cores só dos tokens do DESIGN.md: top `var(--hue-violet)`, bottom `var(--hue-orange)`, manual `var(--hue-ultramarine)`, fora de foco `var(--line-strong)`. A escala do mapa vai de `#fcfbf8` (leaf, 0) a `#6d4bc4` (violet, 1).
- Os números seguem o formato do `ScoreCell` (`toFixed(2)`, com ponto). O vão usa o sinal tipográfico: `−0.31` / `+0.05`.
- Classes CSS novas com prefixo `ditto-chart-`, em `frontend/src/styles/global.css`.
- O foco padrão é `Top e bottom`, N = 3, métrica "Média". N vai de 1 a 10. Top e bottom saem sempre do ranking pela **média**.
- Os testes não tocam a rede. Rode com `cd frontend && npx vitest run <arquivo>`.

## Review Focus

1. **Métrica que falhou em parte das perguntas** (linhas sem aquela chave em `scores`): a média usa só o que existe e o tooltip mostra "n = X de Y perguntas". Teste na Task 2 (`metricValue`).
2. **Linhas sem nenhuma métrica** (`scores: {}`): nada de `NaN` em coordenadas. A combinação vai para o fim do ranking, fica fora da dispersão e aparece como "—" no mapa. Testes nas Tasks 3 (`costPoints`, `questionMatrix`) e 6 (célula vazia).
3. **Experimento rodando:** combinações aparecem a cada polling, e uma combinação marcada à mão pode não existir mais. Ela é ignorada sem quebrar nada. Teste na Task 2 (`focusSet`).
4. **A métrica escolhida some** (por exemplo, ao abrir outro experimento): a barra volta para "Média". Teste na Task 4.
5. **Experimentos antigos sem latência ou tokens** (valores 0): a Fig. 3 troca para o custo que existe ou dá lugar a uma nota. Teste na Task 5.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `frontend/src/experiments/ranking.ts` (novo) | `MEDIA_KEY`, `DIMS`, `mean`, `rowMedia`, `comboKey`, `comboText`, `dimName`, `groupByCombo`, `RankRow`, `rankCombinations`, `rankByMedia`. Sai de `ExperimentDetailPage.tsx`. |
| `frontend/src/components/charts/aggregate.ts` (novo) | Tipos de foco e funções puras de cada figura |
| `frontend/src/components/charts/testFixture.ts` (novo) | Resultados sintéticos compartilhados pelos testes |
| `frontend/src/components/charts/primitives.tsx` (novo) | Cores por grupo, formatação, `useChartWidth`, `ChartFrame`, `RankMark`, `AxisBottom`, `AxisLeft`, `ComboTip` |
| `frontend/src/components/charts/FocusBar.tsx` (novo) | Controles do foco |
| `frontend/src/components/charts/ChartsPanel.tsx` (novo) | Monta a barra e as figuras |
| `frontend/src/components/charts/MetricProfile.tsx` (novo) | Fig. 1 |
| `frontend/src/components/charts/DimensionEffects.tsx` (novo) | Fig. 2 |
| `frontend/src/components/charts/CostQuality.tsx` (novo) | Fig. 3 |
| `frontend/src/components/charts/Stability.tsx` (novo) | Fig. 4a + 4b |
| `frontend/src/pages/ExperimentDetailPage.tsx` | Usa `ranking.ts`, guarda o foco e ganha a aba "Gráficos" |
| `frontend/src/styles/global.css` | Estilos `ditto-chart-*` |

---

### Task 1: Extrair o ranking para `experiments/ranking.ts`

**Files:**
- Create: `frontend/src/experiments/ranking.ts`
- Create: `frontend/src/experiments/ranking.test.ts`
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx` (linhas 15–73 e o `useMemo` de `rankingByMedia`)

**Interfaces:**
- Consumes: `ExperimentResultRow` (`api/types.ts`), `Combination` (`components/Score.tsx`), `term` (`glossary.ts`)
- Produces:
  ```ts
  export const MEDIA_KEY = "__media__";
  export type Dim = keyof Combination;
  export const DIMS: Dim[];
  export function mean(values: number[]): number | null;
  export function rowMedia(row: ExperimentResultRow): number | null;
  export function comboKey(c: Combination): string;
  export function dimName(dim: Dim, key: string): string;
  export function comboText(c: Combination): string;          // "Recursivo · e5 · … · qwen"
  export function groupByCombo(results: ExperimentResultRow[]): Map<string, ExperimentResultRow[]>;
  export interface RankRow { key: string; combo: Combination; count: number; scores: Record<string, number | null>; media: number | null }
  export function rankCombinations(results: ExperimentResultRow[], metricKeys: string[]): RankRow[];
  export function rankByMedia(ranking: RankRow[]): RankRow[];  // cópia ordenada pela média, desc; null por último
  ```

- [ ] **Step 1: Escrever o teste que falha**

`frontend/src/experiments/ranking.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import type { ExperimentResultRow } from "../api/types";
import { comboKey, comboText, groupByCombo, mean, rankByMedia, rankCombinations, rowMedia } from "./ranking";

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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/experiments/ranking.test.ts`
Expected: FAIL com `Failed to resolve import "./ranking"`.

- [ ] **Step 3: Criar `ranking.ts`**

`frontend/src/experiments/ranking.ts`:

```ts
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npx vitest run src/experiments/ranking.test.ts`
Expected: PASS (6 testes).

- [ ] **Step 5: Fazer a página usar o módulo**

Em `frontend/src/pages/ExperimentDetailPage.tsx`:

1. Apague as definições locais de `MEDIA_KEY`, `type Dim`, `DIMS`, `mean`, `rowMedia`, `comboKey`, `dimName`, `interface RankRow` e `rankCombinations` (hoje entre as linhas 15 e 73). Mantenha `PAGE_SIZES` e `experimentDurationMs`.
2. Acrescente aos imports:
   ```ts
   import {
     DIMS, type Dim, MEDIA_KEY, type RankRow, dimName, rankByMedia, rankCombinations, rowMedia,
   } from "../experiments/ranking";
   ```
3. Troque o `useMemo` de `rankingByMedia` por:
   ```ts
   const rankingByMedia = useMemo(() => rankByMedia(ranking), [ranking]);
   ```
4. No import de `../components/Score`, mantenha `type Combination` (ele ainda é usado por `showAnswersOf`).

- [ ] **Step 6: Rodar os testes da página e o typecheck**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetailPage.test.tsx src/experiments && npx tsc -b`
Expected: todos PASS; `tsc` sem erros.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/experiments frontend/src/pages/ExperimentDetailPage.tsx
git commit -m "refactor(experiments): extract combination ranking into a shared module"
```

---

### Task 2: Foco e perfil de métricas (`aggregate.ts`, parte 1)

**Files:**
- Modify: `frontend/package.json` (dependências d3)
- Create: `frontend/src/components/charts/aggregate.ts`
- Create: `frontend/src/components/charts/testFixture.ts`
- Create: `frontend/src/components/charts/aggregate.test.ts`

**Interfaces:**
- Consumes: tudo o que a Task 1 produz em `experiments/ranking.ts`.
- Produces:
  ```ts
  export type FocusMode = "top_bottom" | "top" | "all";
  export interface FocusState { mode: FocusMode; n: number; metric: string; manual: string[] } // manual = comboKeys
  export const DEFAULT_FOCUS: FocusState;           // { mode: "top_bottom", n: 3, metric: MEDIA_KEY, manual: [] }
  export type Group = "top" | "bottom" | "manual";
  export interface FocusedCombo { row: RankRow; place: number; group: Group }
  export function metricLabel(metric: string): string;               // MEDIA_KEY → "Média"
  export function rowValue(row: ExperimentResultRow, metric: string): number | null;
  export interface MetricValue { value: number | null; n: number; total: number }
  export function metricValue(rows: ExperimentResultRow[], metric: string): MetricValue;
  export function focusSet(ranked: RankRow[], focus: FocusState): FocusedCombo[]; // ranked = rankByMedia(...)
  export interface ProfilePoint extends MetricValue { combo: FocusedCombo }
  export interface ProfileLine { metric: string; points: ProfilePoint[]; topMean: number | null; bottomMean: number | null; gap: number | null }
  export function metricProfile(results: ExperimentResultRow[], focused: FocusedCombo[], metricKeys: string[]): ProfileLine[];
  ```
  `testFixture.ts` exporta `fixture(): ExperimentResultRow[]`, com 8 combinações e 2 perguntas cada (ver o código).

- [ ] **Step 1: Instalar as dependências**

Run: `cd frontend && npm install d3-scale d3-array && npm install -D @types/d3-scale @types/d3-array`
Expected: `package.json` e `package-lock.json` atualizados, sem erros.

- [ ] **Step 2: Criar o fixture dos testes**

`frontend/src/components/charts/testFixture.ts`:

```ts
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
```

- [ ] **Step 3: Escrever os testes que falham**

`frontend/src/components/charts/aggregate.test.ts`:

```ts
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
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/components/charts/aggregate.test.ts`
Expected: FAIL com `Failed to resolve import "./aggregate"`.

- [ ] **Step 5: Criar `aggregate.ts` (parte 1)**

`frontend/src/components/charts/aggregate.ts`:

```ts
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
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd frontend && npx vitest run src/components/charts/aggregate.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/charts
git commit -m "feat(charts): focus set and metric profile aggregation"
```

---

### Task 3: Efeitos, custo, quartis e mapa (`aggregate.ts`, parte 2)

**Files:**
- Modify: `frontend/src/components/charts/aggregate.ts` (acrescentar no fim)
- Modify: `frontend/src/components/charts/aggregate.test.ts` (acrescentar no fim)

**Interfaces:**
- Consumes: Task 1 (`DIMS`, `Dim`, `comboKey`, `groupByCombo`, `mean`) e Task 2 (`FocusedCombo`, `metricValue`, `rowValue`).
- Produces:
  ```ts
  export const DIM_LABEL: Record<Dim, string>;   // DIMENSION_LABEL + llm: "Modelo (LLM)"
  export interface OptionEffect { option: string; mean: number; min: number; max: number; combos: number }
  export interface DimensionEffect { dim: Dim; options: OptionEffect[]; effect: number }
  export interface DimensionEffects { varying: DimensionEffect[]; fixed: { dim: Dim; option: string }[]; incompleteGrid: boolean }
  export function dimensionEffects(results: ExperimentResultRow[], metric: string): DimensionEffects;
  export type CostKind = "latency" | "tokens";
  export const COST_LABEL: Record<CostKind, string>;
  export function hasCost(results: ExperimentResultRow[], cost: CostKind): boolean;
  export interface CostPoint { key: string; combo: Combination; cost: number; quality: number }
  export function costPoints(results: ExperimentResultRow[], cost: CostKind, metric: string): CostPoint[];
  export function paretoFrontier<T extends { cost: number; quality: number }>(points: T[]): T[];
  export function quartiles(values: number[]): { q1: number; median: number; q3: number } | null;
  export interface MatrixCell { value: number | null; row: ExperimentResultRow | null }
  export interface MatrixRow { question: string; difficulty: number | null; cells: MatrixCell[] } // cells alinhadas com `focused`
  export function questionMatrix(results: ExperimentResultRow[], focused: FocusedCombo[], metric: string): MatrixRow[];
  ```

- [ ] **Step 1: Escrever os testes que falham**

Acrescente ao fim de `aggregate.test.ts` (e junte os novos nomes ao import de `./aggregate`: `costPoints, dimensionEffects, hasCost, paretoFrontier, quartiles, questionMatrix`):

```ts
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
    expect(full.incompleteGrid).toBe(false);
    const missing = fixture().filter((r) => !(r.chunking === "recursive" && r.rag === "naive" && r.llm === "qwen"));
    expect(dimensionEffects(missing, MEDIA_KEY).incompleteGrid).toBe(true);
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/components/charts/aggregate.test.ts`
Expected: FAIL: `dimensionEffects is not a function` (e os demais).

- [ ] **Step 3: Implementar**

No topo de `aggregate.ts`, troque os imports por:

```ts
import { quantileSorted } from "d3-array";

import type { ExperimentResultRow } from "../../api/types";
import {
  DIMS, type Dim, MEDIA_KEY, type RankRow, comboKey, groupByCombo, mean, rowMedia,
} from "../../experiments/ranking";
import { DIMENSION_LABEL, term } from "../../glossary";
import type { Combination } from "../Score";
```

Acrescente ao fim do arquivo:

```ts
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
    if (options.length < 2) continue;
    varying.push({ dim, options, effect: options[0].mean - options[options.length - 1].mean });
  }
  varying.sort((a, b) => b.effect - a.effect);
  return { varying, fixed, incompleteGrid: combos.length < gridSize };
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
```

Remova do import de `experiments/ranking` qualquer nome que o linter/tsc acuse como não usado.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npx vitest run src/components/charts/aggregate.test.ts && npx tsc -b`
Expected: PASS; `tsc` sem erros.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/charts
git commit -m "feat(charts): dimension effects, cost frontier, quartiles and question matrix"
```

---

### Task 4: Primitivas, barra de foco, Figura 1 e a aba na página

**Files:**
- Create: `frontend/src/components/charts/primitives.tsx`
- Create: `frontend/src/components/charts/FocusBar.tsx`
- Create: `frontend/src/components/charts/MetricProfile.tsx`
- Create: `frontend/src/components/charts/ChartsPanel.tsx`
- Create: `frontend/src/components/charts/ChartsPanel.test.tsx`
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx`
- Modify: `frontend/src/pages/ExperimentDetailPage.test.tsx`
- Modify: `frontend/src/styles/global.css` (acrescentar no fim)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  ```ts
  // primitives.tsx
  export const GROUP_COLOR: Record<Group, string>;
  export const GROUP_LABEL: Record<Group, string>;          // "Melhores" | "Piores" | "Escolhidas"
  export function formatScore(v: number | null): string;     // "0.85" | "—"
  export function formatGap(v: number): string;              // "−0.31" | "+0.05"
  export function nText(n: number, total: number): string;   // "n = 7 de 10 perguntas" | "10 perguntas"
  export function useChartWidth(fallback?: number): readonly [RefObject<HTMLDivElement>, number];
  export type Tip = { x: number; y: number; content: ReactNode } | null;
  export function ChartFrame(p: { frameRef: RefObject<HTMLDivElement>; tip: Tip; children: ReactNode }): JSX.Element;
  export function RankMark(p: { x: number; y: number; place: number; group: Group; label: string; onActivate?: () => void; onTip?: (t: Tip) => void; tip?: ReactNode }): JSX.Element;
  export function AxisBottom(p: { scale: ScaleLinear<number, number>; y: number; ticks?: number; gridTop?: number; format?: (v: number) => string }): JSX.Element;
  export function AxisLeft(p: { scale: ScaleLinear<number, number>; x: number; ticks?: number; gridRight?: number; format?: (v: number) => string }): JSX.Element;
  export function ComboTip(p: { combo: Combination; place: number; lines: [string, string][] }): JSX.Element;
  // ChartsPanel.tsx
  export interface ChartsPanelProps {
    results: ExperimentResultRow[]; metricKeys: string[]; ranked: RankRow[];
    focus: FocusState; onFocusChange: (f: FocusState) => void;
    partial: { completed: number; total: number } | null;
    onShowAnswers: (combo: Combination) => void; onOpenRow: (row: ExperimentResultRow) => void;
  }
  export function ChartsPanel(p: ChartsPanelProps): JSX.Element;
  ```
  Rótulo acessível das marcas da Fig. 1: `#<place> <métrica> <valor>`, por exemplo `#1 Média 0.80`.

- [ ] **Step 1: Escrever os testes que falham**

`frontend/src/components/charts/ChartsPanel.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExperimentResultRow } from "../../api/types";
import { rankByMedia, rankCombinations } from "../../experiments/ranking";
import { DEFAULT_FOCUS, type FocusState } from "./aggregate";
import { ChartsPanel } from "./ChartsPanel";
import { fixture } from "./testFixture";

const onShowAnswers = vi.fn();
const onOpenRow = vi.fn();

function Harness({
  results = fixture(),
  initial = DEFAULT_FOCUS,
  partial = null,
}: {
  results?: ExperimentResultRow[];
  initial?: FocusState;
  partial?: { completed: number; total: number } | null;
}) {
  const [focus, setFocus] = useState(initial);
  const metricKeys = [...new Set(results.flatMap((r) => Object.keys(r.scores)))].sort();
  const ranked = rankByMedia(rankCombinations(results, metricKeys));
  return (
    <ChartsPanel
      results={results} metricKeys={metricKeys} ranked={ranked}
      focus={focus} onFocusChange={setFocus} partial={partial}
      onShowAnswers={onShowAnswers} onOpenRow={onOpenRow}
    />
  );
}

function renderPanel(props: Parameters<typeof Harness>[0] = {}) {
  return render(
    <MantineProvider>
      <Harness {...props} />
    </MantineProvider>,
  );
}

const mediaMark = (place: number) => screen.queryByRole("button", { name: new RegExp(`^#${place} Média `) });

beforeEach(() => {
  onShowAnswers.mockReset();
  onOpenRow.mockReset();
});

describe("ChartsPanel · focus and figure 1", () => {
  it("shows top 3 and bottom 3 by default", () => {
    renderPanel();
    for (const p of [1, 2, 3, 6, 7, 8]) expect(mediaMark(p)).toBeInTheDocument();
    expect(mediaMark(4)).not.toBeInTheDocument();
    expect(mediaMark(1)).toHaveAttribute("data-group", "top");
    expect(mediaMark(8)).toHaveAttribute("data-group", "bottom");
  });

  it("switching to top only drops the bottom", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("radio", { name: "Só top" }));
    expect(mediaMark(8)).not.toBeInTheDocument();
    expect(mediaMark(3)).toBeInTheDocument();
  });

  it("changing N changes the marks", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getAllByLabelText("N")[0]);
    await user.click(await screen.findByRole("option", { name: "1" }));
    expect(mediaMark(2)).not.toBeInTheDocument();
    expect(mediaMark(1)).toBeInTheDocument();
    expect(mediaMark(8)).toBeInTheDocument();
  });

  it("a manual pick joins as its own group", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getAllByLabelText("Adicionar combinações")[0]);
    await user.click(await screen.findByRole("option", { name: /^#4 / }));
    expect(mediaMark(4)).toHaveAttribute("data-group", "manual");
  });

  it("clicking or pressing Enter on a mark shows that combination's answers", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(mediaMark(1)!);
    expect(onShowAnswers).toHaveBeenCalledWith(
      expect.objectContaining({ chunking: "token", rag: "agentic", llm: "gemma" }),
    );
    mediaMark(8)!.focus();
    await user.keyboard("{Enter}");
    expect(onShowAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ chunking: "recursive", rag: "naive", llm: "qwen" }),
    );
  });

  it("falls back to Média when the chosen metric is gone", () => {
    renderPanel({ initial: { ...DEFAULT_FOCUS, metric: "context_recall" } });
    expect(screen.getAllByLabelText("Métrica dos gráficos")[0]).toHaveValue("Média");
  });

  it("marks partial results in the captions", () => {
    renderPanel({ partial: { completed: 3, total: 8 } });
    expect(screen.getAllByText(/parcial: 3 de 8 combinações/i).length).toBeGreaterThan(0);
  });

  it("has a screen-reader table for figure 1", () => {
    renderPanel();
    const table = screen.getByRole("table", { name: /figura 1/i });
    expect(within(table).getAllByRole("row").length).toBe(4); // header + 2 metrics + média
  });
});
```

Em `frontend/src/pages/ExperimentDetailPage.test.tsx`, acrescente dentro do `describe`:

```tsx
  it("has a Gráficos tab whose focus survives switching tabs", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    await user.click(await screen.findByRole("radio", { name: "Só top" }));
    await openAnswers(user);
    await user.click(screen.getByRole("tab", { name: /gráficos/i }));
    expect(await screen.findByRole("radio", { name: "Só top" })).toBeChecked();
  });
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/components/charts/ChartsPanel.test.tsx src/pages/ExperimentDetailPage.test.tsx`
Expected: FAIL: `Failed to resolve import "./ChartsPanel"`, e na página nenhuma aba "Gráficos".

- [ ] **Step 3: Criar `primitives.tsx`**

```tsx
/** Shared SVG building blocks for the charts tab. */
import type { ScaleLinear } from "d3-scale";
import { Fragment, type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

import { type Combination, Traits } from "../Score";
import type { Group } from "./aggregate";

export const GROUP_COLOR: Record<Group, string> = {
  top: "var(--hue-violet)",
  bottom: "var(--hue-orange)",
  manual: "var(--hue-ultramarine)",
};

export const GROUP_LABEL: Record<Group, string> = {
  top: "Melhores",
  bottom: "Piores",
  manual: "Escolhidas",
};

export function formatScore(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

export function formatGap(v: number): string {
  return `${v < 0 ? "−" : "+"}${Math.abs(v).toFixed(2)}`;
}

export function nText(n: number, total: number): string {
  return n < total ? `n = ${n} de ${total} perguntas` : `${total} ${total === 1 ? "pergunta" : "perguntas"}`;
}

/** Container width, tracked with ResizeObserver; `fallback` until measured (and in jsdom). */
export function useChartWidth(fallback = 720) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      if (el.clientWidth > 0) setWidth(el.clientWidth);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export type Tip = { x: number; y: number; content: ReactNode } | null;

export function ChartFrame({
  frameRef,
  tip,
  children,
}: {
  frameRef: RefObject<HTMLDivElement>;
  tip: Tip;
  children: ReactNode;
}) {
  return (
    <div ref={frameRef} className="ditto-chart">
      {children}
      {tip && (
        <div className="ditto-chart-tip" role="tooltip" style={{ left: tip.x, top: tip.y }}>
          {tip.content}
        </div>
      )}
    </div>
  );
}

/** A combination's mark: its ranking place in a disc of its group's colour. */
export function RankMark({
  x, y, place, group, label, onActivate, onTip, tip,
}: {
  x: number;
  y: number;
  place: number;
  group: Group;
  label: string;
  onActivate?: () => void;
  onTip?: (t: Tip) => void;
  tip?: ReactNode;
}) {
  const show = () => onTip?.(tip ? { x, y, content: tip } : null);
  const hide = () => onTip?.(null);
  return (
    <g
      className="ditto-chart-mark"
      data-group={group}
      transform={`translate(${x},${y})`}
      role={onActivate ? "button" : "img"}
      tabIndex={onActivate ? 0 : undefined}
      aria-label={label}
      onClick={onActivate}
      onKeyDown={(e) => {
        if (onActivate && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onActivate();
        }
      }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <circle r={10} fill={GROUP_COLOR[group]} />
      <text textAnchor="middle" dy="0.35em">
        {place}
      </text>
    </g>
  );
}

export function AxisBottom({
  scale, y, ticks = 5, gridTop, format = formatScore,
}: {
  scale: ScaleLinear<number, number>;
  y: number;
  ticks?: number;
  gridTop?: number;
  format?: (v: number) => string;
}) {
  const [x0, x1] = scale.range();
  return (
    <g className="ditto-chart-axis" aria-hidden>
      <line x1={x0} x2={x1} y1={y} y2={y} />
      {scale.ticks(ticks).map((t) => (
        <g key={t} transform={`translate(${scale(t)},${y})`}>
          {gridTop !== undefined && <line className="ditto-chart-grid" y1={gridTop - y} y2={0} />}
          <line y2={4} />
          <text y={16} textAnchor="middle">
            {format(t)}
          </text>
        </g>
      ))}
    </g>
  );
}

export function AxisLeft({
  scale, x, ticks = 5, gridRight, format = formatScore,
}: {
  scale: ScaleLinear<number, number>;
  x: number;
  ticks?: number;
  gridRight?: number;
  format?: (v: number) => string;
}) {
  const [y0, y1] = scale.range();
  return (
    <g className="ditto-chart-axis" aria-hidden>
      <line x1={x} x2={x} y1={y0} y2={y1} />
      {scale.ticks(ticks).map((t) => (
        <g key={t} transform={`translate(${x},${scale(t)})`}>
          {gridRight !== undefined && <line className="ditto-chart-grid" x1={0} x2={gridRight - x} />}
          <line x2={-4} />
          <text x={-8} dy="0.32em" textAnchor="end">
            {format(t)}
          </text>
        </g>
      ))}
    </g>
  );
}

export function ComboTip({ combo, place, lines }: { combo: Combination; place: number; lines: [string, string][] }) {
  return (
    <>
      <div className="ditto-chart-tip-title">#{place}</div>
      <Traits combo={combo} />
      <dl className="ditto-kv">
        {lines.map(([k, v]) => (
          <Fragment key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </Fragment>
        ))}
      </dl>
    </>
  );
}
```

- [ ] **Step 4: Criar `FocusBar.tsx`**

```tsx
import { MultiSelect, SegmentedControl, Select } from "@mantine/core";

import { MEDIA_KEY, type RankRow, comboText } from "../../experiments/ranking";
import { type FocusMode, type FocusState, metricLabel } from "./aggregate";

const N_OPTIONS = Array.from({ length: 10 }, (_, i) => String(i + 1));

export function FocusBar({
  focus, onChange, ranked, metricKeys,
}: {
  focus: FocusState;
  onChange: (f: FocusState) => void;
  ranked: RankRow[];
  metricKeys: string[];
}) {
  const set = (patch: Partial<FocusState>) => onChange({ ...focus, ...patch });
  return (
    <div className="ditto-filters ditto-chart-focus" role="group" aria-label="Combinações em foco">
      <div className="ditto-chart-focus-mode">
        <span className="ditto-chart-focus-label">Mostrar</span>
        <SegmentedControl
          size="sm"
          value={focus.mode}
          onChange={(v) => set({ mode: v as FocusMode })}
          data={[
            { value: "top_bottom", label: "Top e bottom" },
            { value: "top", label: "Só top" },
            { value: "all", label: "Todas" },
          ]}
        />
      </div>
      <Select
        label="N"
        size="sm"
        w={80}
        data={N_OPTIONS}
        value={String(focus.n)}
        onChange={(v) => set({ n: Number(v ?? 3) })}
        allowDeselect={false}
        disabled={focus.mode === "all"}
      />
      <Select
        label="Métrica dos gráficos"
        size="sm"
        data={[{ value: MEDIA_KEY, label: "Média" }, ...metricKeys.map((k) => ({ value: k, label: metricLabel(k) }))]}
        value={focus.metric}
        onChange={(v) => set({ metric: v ?? MEDIA_KEY })}
        allowDeselect={false}
      />
      <MultiSelect
        label="Adicionar combinações"
        placeholder="Escolha no ranking"
        size="sm"
        searchable
        clearable
        data={ranked.map((r, i) => ({ value: r.key, label: `#${i + 1} ${comboText(r.combo)}` }))}
        value={focus.manual}
        onChange={(v) => set({ manual: v })}
      />
    </div>
  );
}
```

- [ ] **Step 5: Criar `MetricProfile.tsx`**

```tsx
import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { MEDIA_KEY } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { type Group, type ProfileLine, metricLabel } from "./aggregate";
import {
  AxisBottom, ChartFrame, ComboTip, RankMark, type Tip, formatGap, formatScore, nText, useChartWidth,
} from "./primitives";

const LABEL_W = 170;
const GAP_W = 64;
const ROW_H = 40;
const TOP = 8;
const AXIS_H = 28;
/** Top above the line, bottom below, manual on it, so the groups rarely collide. */
const OFFSET: Record<Group, number> = { top: -7, bottom: 7, manual: 0 };

export function MetricProfile({
  lines, showGap, onShowAnswers,
}: {
  lines: ProfileLine[];
  showGap: boolean;
  onShowAnswers: (combo: Combination) => void;
}) {
  const [ref, width] = useChartWidth();
  const [tip, setTip] = useState<Tip>(null);
  const x = scaleLinear().domain([0, 1]).range([LABEL_W, Math.max(LABEL_W + 120, width - GAP_W)]);
  const bottom = TOP + lines.length * ROW_H;
  const combos = lines[0]?.points.map((p) => p.combo) ?? [];

  return (
    <ChartFrame frameRef={ref} tip={tip}>
      <svg width={width} height={bottom + AXIS_H} role="group" aria-label="Figura 1: perfil de métricas">
        <AxisBottom scale={x} y={bottom} gridTop={TOP} />
        {lines.map((line, i) => {
          const cy = TOP + i * ROW_H + ROW_H / 2;
          const name = metricLabel(line.metric);
          return (
            <g key={line.metric} className="ditto-chart-row" data-media={line.metric === MEDIA_KEY || undefined}>
              <text x={LABEL_W - 12} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-label">
                {name}
              </text>
              {showGap && line.topMean !== null && line.bottomMean !== null && line.gap !== null && (
                <>
                  <rect
                    className="ditto-chart-gap"
                    x={x(Math.min(line.topMean, line.bottomMean))}
                    y={cy - 12}
                    width={Math.abs(x(line.topMean) - x(line.bottomMean))}
                    height={24}
                  />
                  <text x={width - 8} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-gap-value">
                    {formatGap(line.gap)}
                  </text>
                </>
              )}
              {line.points.map((p) =>
                p.value === null ? null : (
                  <RankMark
                    key={p.combo.row.key}
                    x={x(p.value)}
                    y={cy + OFFSET[p.combo.group]}
                    place={p.combo.place}
                    group={p.combo.group}
                    label={`#${p.combo.place} ${name} ${formatScore(p.value)}`}
                    onActivate={() => onShowAnswers(p.combo.row.combo)}
                    onTip={setTip}
                    tip={
                      <ComboTip
                        combo={p.combo.row.combo}
                        place={p.combo.place}
                        lines={[[name, formatScore(p.value)], ["Perguntas", nText(p.n, p.total)]]}
                      />
                    }
                  />
                ),
              )}
            </g>
          );
        })}
      </svg>
      <table className="visually-hidden">
        <caption>Figura 1: perfil de métricas das combinações em foco</caption>
        <thead>
          <tr>
            <th scope="col">Métrica</th>
            {combos.map((c) => (
              <th key={c.row.key} scope="col">#{c.place}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.metric}>
              <th scope="row">{metricLabel(line.metric)}</th>
              {line.points.map((p) => (
                <td key={p.combo.row.key}>{formatScore(p.value)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ChartFrame>
  );
}
```

- [ ] **Step 6: Criar `ChartsPanel.tsx`**

```tsx
import { useMemo } from "react";

import type { ExperimentResultRow } from "../../api/types";
import { MEDIA_KEY, type RankRow } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { type FocusState, type Group, focusSet, metricProfile } from "./aggregate";
import { FocusBar } from "./FocusBar";
import { MetricProfile } from "./MetricProfile";
import { GROUP_COLOR, GROUP_LABEL } from "./primitives";

export interface ChartsPanelProps {
  results: ExperimentResultRow[];
  metricKeys: string[];
  /** Combinations sorted by média desc (rankByMedia). */
  ranked: RankRow[];
  focus: FocusState;
  onFocusChange: (f: FocusState) => void;
  partial: { completed: number; total: number } | null;
  onShowAnswers: (combo: Combination) => void;
  onOpenRow: (row: ExperimentResultRow) => void;
}

export function ChartsPanel({
  results, metricKeys, ranked, focus, onFocusChange, partial, onShowAnswers,
}: ChartsPanelProps) {
  // A metric the experiment no longer has falls back to the média.
  const metric = focus.metric === MEDIA_KEY || metricKeys.includes(focus.metric) ? focus.metric : MEDIA_KEY;
  const effective = metric === focus.metric ? focus : { ...focus, metric };

  const focused = useMemo(() => focusSet(ranked, effective), [ranked, effective]);
  const profile = useMemo(() => metricProfile(results, focused, metricKeys), [results, focused, metricKeys]);
  const groups = [...new Set(focused.map((f) => f.group))] as Group[];
  const showGap = groups.includes("bottom");
  const suffix = partial ? ` Parcial: ${partial.completed} de ${partial.total} combinações.` : "";

  return (
    <div className="ditto-charts">
      <FocusBar focus={effective} onChange={onFocusChange} ranked={ranked} metricKeys={metricKeys} />
      <ul className="ditto-chart-legend" aria-label="Grupos">
        {groups.map((g) => (
          <li key={g}>
            <span className="ditto-chart-swatch" style={{ background: GROUP_COLOR[g] }} aria-hidden />
            {GROUP_LABEL[g]}
          </li>
        ))}
        <li className="ditto-muted">O número é a posição no ranking pela média.</li>
      </ul>

      <figure className="ditto-chart-figure">
        <figcaption className="ditto-caption">
          <strong>Figura 1.</strong> Perfil de métricas das combinações em foco.
          {showGap && " A faixa marca o vão entre a média das melhores e a das piores; as métricas estão ordenadas pelo maior vão."}
          {suffix}
        </figcaption>
        <MetricProfile lines={profile} showGap={showGap} onShowAnswers={onShowAnswers} />
      </figure>
    </div>
  );
}
```

`onOpenRow` faz parte das props desde já (a página o passa), mas só é desestruturado na Task 6, que o usa.

- [ ] **Step 7: Ligar a aba na página**

Em `frontend/src/pages/ExperimentDetailPage.tsx`:

1. Imports:
   ```ts
   import { ChartsPanel } from "../components/charts/ChartsPanel";
   import { DEFAULT_FOCUS, type FocusState } from "../components/charts/aggregate";
   ```
2. Junto dos outros `useState`:
   ```ts
   const [focus, setFocus] = useState<FocusState>(DEFAULT_FOCUS);
   ```
3. No `Tabs.List`, entre "Ranking das combinações" e "Respostas por pergunta":
   ```tsx
   <Tabs.Tab value="charts">Gráficos</Tabs.Tab>
   ```
4. Depois do `</Tabs.Panel>` do ranking:
   ```tsx
   <Tabs.Panel value="charts">
     <ChartsPanel
       results={results}
       metricKeys={metricKeys}
       ranked={rankingByMedia}
       focus={focus}
       onFocusChange={setFocus}
       partial={
         isRunning && detail.progress && detail.progress.total > 0
           ? { completed: detail.progress.completed, total: detail.progress.total }
           : null
       }
       onShowAnswers={showAnswersOf}
       onOpenRow={setOpenRow}
     />
   </Tabs.Panel>
   ```

- [ ] **Step 8: Estilos**

Acrescente ao fim de `frontend/src/styles/global.css`:

```css
/* ---- Charts tab */
.ditto-charts { display: flex; flex-direction: column; gap: 28px; }
.ditto-chart-focus { align-items: flex-end; }
.ditto-chart-focus-mode { display: flex; flex-direction: column; gap: 4px; }
.ditto-chart-focus-label { font-size: 14px; font-weight: 650; }
.ditto-chart-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: -12px 0 0; padding: 0; list-style: none; font-size: 13px; }
.ditto-chart-legend li { display: inline-flex; align-items: center; gap: 6px; }
.ditto-chart-swatch { width: 10px; height: 10px; border-radius: 50%; }
.ditto-chart-figure { margin: 0; }
.ditto-chart { position: relative; width: 100%; }
.ditto-chart svg { display: block; overflow: visible; }
.ditto-chart svg text { font-size: 12px; fill: var(--ink-2); font-feature-settings: "tnum" 1; }
.ditto-chart-axis line { stroke: var(--ink); stroke-width: 1; }
.ditto-chart-axis .ditto-chart-grid { stroke: var(--line); }
.ditto-chart svg .ditto-chart-label { fill: var(--ink); font-size: 13px; }
.ditto-chart-row[data-media] .ditto-chart-label { font-weight: 700; }
.ditto-chart-gap { fill: var(--binder); }
.ditto-chart svg .ditto-chart-gap-value { fill: var(--ink); font-weight: 650; }
.ditto-chart-mark { cursor: pointer; outline: none; }
.ditto-chart-mark text { fill: var(--ink-inverse); font-size: 11px; font-weight: 750; pointer-events: none; }
.ditto-chart-mark[data-group="bottom"] text { fill: var(--ink); }
.ditto-chart-mark:focus-visible circle, .ditto-chart-mark:hover circle { stroke: var(--ink); stroke-width: 2; }
.ditto-chart-tip {
  position: absolute; z-index: 5; transform: translate(-50%, calc(-100% - 16px));
  min-width: 220px; max-width: 340px; padding: 10px 12px;
  background: var(--field); border: 1px solid var(--ink); border-radius: 2px;
  box-shadow: var(--leaf-shadow); font-size: 13px; pointer-events: none;
}
.ditto-chart-tip-title { font-weight: 750; margin-bottom: 4px; }
.ditto-chart-tip .ditto-kv { margin: 8px 0 0; }
```

- [ ] **Step 9: Rodar e ver passar**

Run: `cd frontend && npx vitest run src/components/charts src/pages/ExperimentDetailPage.test.tsx && npx tsc -b`
Expected: todos PASS; `tsc` sem erros.

- [ ] **Step 10: Commit**

```bash
git add frontend/src
git commit -m "feat(charts): charts tab with focus bar and metric profile figure"
```

---

### Task 5: Figuras 2 e 3 (efeito por dimensão e custo × qualidade)

**Files:**
- Create: `frontend/src/components/charts/DimensionEffects.tsx`
- Create: `frontend/src/components/charts/CostQuality.tsx`
- Modify: `frontend/src/components/charts/ChartsPanel.tsx`
- Modify: `frontend/src/components/charts/ChartsPanel.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: Task 3 (`dimensionEffects`, `DIM_LABEL`, `costPoints`, `paretoFrontier`, `hasCost`, `COST_LABEL`, `CostKind`, `CostPoint`), Task 4 (primitivas).
- Produces:
  ```ts
  export function DimensionEffects(p: { effects: DimensionEffects; metric: string }): JSX.Element;
  export function CostQuality(p: {
    points: CostPoint[]; cost: CostKind; onCostChange: (c: CostKind) => void;
    available: Record<CostKind, boolean>; focused: FocusedCombo[]; ranked: RankRow[]; metric: string;
    onShowAnswers: (combo: Combination) => void;
  }): JSX.Element;
  ```
  Rótulo das marcas da Fig. 3: `#<place> <COST_LABEL> <custo> · <métrica> <valor>` mais ` · fronteira de Pareto` quando a marca está na fronteira. Painéis da Fig. 2: `<section aria-label="<DIM_LABEL>: efeito <x.xx>">`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente ao fim de `ChartsPanel.test.tsx`:

```tsx
describe("ChartsPanel · figures 2 and 3", () => {
  it("orders dimension panels by effect and lists fixed ones", () => {
    renderPanel();
    const panels = screen.getAllByRole("region", { name: /: efeito/ }).map((p) => p.getAttribute("aria-label"));
    expect(panels).toEqual(["Corte: efeito 0.40", "Técnica de RAG: efeito 0.20", "Modelo (LLM): efeito 0.10"]);
    expect(screen.getByText(/fixo neste experimento: embedding .*, busca /i)).toBeInTheDocument();
    expect(screen.queryByText(/grade incompleta/i)).not.toBeInTheDocument();
  });

  it("warns about an incomplete grid", () => {
    renderPanel({ results: fixture().filter((r) => !(r.chunking === "recursive" && r.rag === "naive" && r.llm === "qwen")) });
    expect(screen.getByText(/grade incompleta/i)).toBeInTheDocument();
  });

  it("rings the Pareto frontier, focused or not", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /^#2 Latência.*fronteira de Pareto/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^#3 Latência.*fronteira de Pareto/ })).not.toBeInTheDocument();
    const table = screen.getByRole("table", { name: /figura 3/i });
    const row5 = within(table).getAllByRole("row").find((r) => r.textContent?.startsWith("#5"));
    expect(row5).toHaveTextContent("sim");
  });

  it("falls back to tokens when latency is missing, and to a note when both are", () => {
    const noLatency = fixture().map((r) => ({ ...r, latency_ms: 0 }));
    const { unmount } = renderPanel({ results: noLatency });
    expect(screen.getAllByText("Tokens médios").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Latência média (ms)")).toHaveLength(0);
    unmount();
    renderPanel({ results: noLatency.map((r) => ({ ...r, tokens: 0 })) });
    expect(screen.getByText(/sem dados de custo neste experimento/i)).toBeInTheDocument();
  });

  it("needs at least two combinations for figures 2 and 3", () => {
    renderPanel({ results: fixture().slice(0, 2) });
    expect(screen.getAllByText(/precisa de ao menos 2 combinações/i)).toHaveLength(2);
    expect(mediaMark(1)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/components/charts/ChartsPanel.test.tsx`
Expected: os 5 testes novos FAIL (nenhuma região "efeito", nenhuma marca "Latência").

- [ ] **Step 3: Criar `DimensionEffects.tsx`**

```tsx
import { scaleLinear } from "d3-scale";

import { dimName } from "../../experiments/ranking";
import { DIM_LABEL, type DimensionEffects as Effects, metricLabel } from "./aggregate";
import { AxisBottom, formatScore } from "./primitives";

const PANEL_W = 360;
const LABEL_W = 130;
const VALUE_W = 44;
const ROW_H = 26;
const PAD = 6;
const AXIS_H = 22;

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function DimensionEffects({ effects, metric }: { effects: Effects; metric: string }) {
  const x = scaleLinear().domain([0, 1]).range([LABEL_W, PANEL_W - VALUE_W]);
  return (
    <div>
      {effects.varying.length > 0 && (
        <div className="ditto-chart-panels">
          {effects.varying.map((d) => {
            const bottom = PAD + d.options.length * ROW_H;
            return (
              <section key={d.dim} className="ditto-chart-panel" aria-label={`${DIM_LABEL[d.dim]}: efeito ${formatScore(d.effect)}`}>
                <h4 className="ditto-chart-panel-title">
                  {DIM_LABEL[d.dim]} <span className="ditto-muted">efeito {formatScore(d.effect)}</span>
                </h4>
                <svg viewBox={`0 0 ${PANEL_W} ${bottom + AXIS_H}`} width="100%" aria-hidden>
                  {d.options.map((o, i) => {
                    const cy = PAD + i * ROW_H + ROW_H / 2;
                    const name = dimName(d.dim, o.option);
                    return (
                      <g key={o.option}>
                        <text x={LABEL_W - 8} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-label">
                          {clip(name, 18)}
                          <title>{name}</title>
                        </text>
                        <line className="ditto-chart-range" x1={x(o.min)} x2={x(o.max)} y1={cy} y2={cy} />
                        <circle className="ditto-chart-dot" cx={x(o.mean)} cy={cy} r={5} />
                        <text x={PANEL_W - 4} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-value">
                          {formatScore(o.mean)}
                        </text>
                      </g>
                    );
                  })}
                  <AxisBottom scale={x} y={bottom} ticks={2} gridTop={PAD} />
                </svg>
              </section>
            );
          })}
        </div>
      )}
      {effects.fixed.length > 0 && (
        <p className="ditto-caption">
          Fixo neste experimento:{" "}
          {effects.fixed.map((f) => `${DIM_LABEL[f.dim]} ${dimName(f.dim, f.option)}`).join(", ")}.
        </p>
      )}
      {effects.incompleteGrid && effects.varying.length > 0 && (
        <p className="ditto-caption">
          <strong>Grade incompleta:</strong> o efeito de uma dimensão pode se misturar com o das outras.
        </p>
      )}
      <table className="visually-hidden">
        <caption>Figura 2: {metricLabel(metric)} por opção de cada dimensão</caption>
        <thead>
          <tr>
            <th scope="col">Dimensão</th>
            <th scope="col">Opção</th>
            <th scope="col">Média</th>
            <th scope="col">Mínimo</th>
            <th scope="col">Máximo</th>
            <th scope="col">Combinações</th>
          </tr>
        </thead>
        <tbody>
          {effects.varying.flatMap((d) =>
            d.options.map((o) => (
              <tr key={`${d.dim}-${o.option}`}>
                <th scope="row">{DIM_LABEL[d.dim]}</th>
                <td>{dimName(d.dim, o.option)}</td>
                <td>{formatScore(o.mean)}</td>
                <td>{formatScore(o.min)}</td>
                <td>{formatScore(o.max)}</td>
                <td>{o.combos}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Criar `CostQuality.tsx`**

```tsx
import { SegmentedControl } from "@mantine/core";
import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { comboText } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { COST_LABEL, type CostKind, type CostPoint, type FocusedCombo, metricLabel, paretoFrontier } from "./aggregate";
import { AxisBottom, AxisLeft, ChartFrame, ComboTip, RankMark, type Tip, formatScore, useChartWidth } from "./primitives";

const M = { top: 12, right: 24, bottom: 44, left: 52 };
const H = 320;

function formatCost(v: number): string {
  return Math.round(v).toLocaleString("pt-BR");
}

export function CostQuality({
  points, cost, onCostChange, available, focused, metric, onShowAnswers,
}: {
  points: CostPoint[];
  cost: CostKind;
  onCostChange: (c: CostKind) => void;
  available: Record<CostKind, boolean>;
  focused: FocusedCombo[];
  metric: string;
  onShowAnswers: (combo: Combination) => void;
}) {
  const [ref, width] = useChartWidth();
  const [tip, setTip] = useState<Tip>(null);
  const frontier = paretoFrontier(points);
  const onFrontier = new Set(frontier.map((p) => p.key));
  const byKey = new Map(focused.map((f) => [f.row.key, f]));
  const placeOf = new Map(focused.map((f) => [f.row.key, f.place]));

  const maxCost = Math.max(...points.map((p) => p.cost), 1);
  const x = scaleLinear().domain([0, maxCost]).nice().range([M.left, width - M.right]);
  const y = scaleLinear().domain([0, 1]).range([H - M.bottom, M.top]);
  const path = frontier
    .map((p, i) => (i === 0 ? `M${x(p.cost)},${y(p.quality)}` : `H${x(p.cost)}V${y(p.quality)}`))
    .join("");
  const muted = points.filter((p) => !byKey.has(p.key));
  const marked = points.filter((p) => byKey.has(p.key));
  const quality = metricLabel(metric);

  return (
    <div>
      <SegmentedControl
        size="xs"
        mb="sm"
        value={cost}
        onChange={(v) => onCostChange(v as CostKind)}
        data={[
          { value: "latency", label: "Latência", disabled: !available.latency },
          { value: "tokens", label: "Tokens", disabled: !available.tokens },
        ]}
        aria-label="Custo"
      />
      <ChartFrame frameRef={ref} tip={tip}>
        <svg width={width} height={H} role="group" aria-label="Figura 3: custo e qualidade">
          <AxisLeft scale={y} x={M.left} gridRight={width - M.right} />
          <AxisBottom scale={x} y={H - M.bottom} format={formatCost} />
          <text x={(M.left + width - M.right) / 2} y={H - 6} textAnchor="middle" className="ditto-chart-label">
            {COST_LABEL[cost]}
          </text>
          <text transform={`translate(14,${(H - M.bottom + M.top) / 2}) rotate(-90)`} textAnchor="middle" className="ditto-chart-label">
            {quality}
          </text>
          <path className="ditto-chart-frontier" d={path} />
          {muted.map((p) => (
            <g key={p.key} transform={`translate(${x(p.cost)},${y(p.quality)})`}>
              {onFrontier.has(p.key) && <circle className="ditto-chart-ring" r={8} />}
              <circle className="ditto-chart-dot-muted" r={4}>
                <title>{`${comboText(p.combo)}: ${formatCost(p.cost)} · ${formatScore(p.quality)}`}</title>
              </circle>
            </g>
          ))}
          {marked.map((p) => {
            const f = byKey.get(p.key) as FocusedCombo;
            const pareto = onFrontier.has(p.key);
            return (
              <g key={p.key}>
                {pareto && <circle className="ditto-chart-ring" cx={x(p.cost)} cy={y(p.quality)} r={14} />}
                <RankMark
                  x={x(p.cost)}
                  y={y(p.quality)}
                  place={f.place}
                  group={f.group}
                  label={`#${f.place} ${COST_LABEL[cost]} ${formatCost(p.cost)} · ${quality} ${formatScore(p.quality)}${pareto ? " · fronteira de Pareto" : ""}`}
                  onActivate={() => onShowAnswers(p.combo)}
                  onTip={setTip}
                  tip={
                    <ComboTip
                      combo={p.combo}
                      place={f.place}
                      lines={[
                        [COST_LABEL[cost], formatCost(p.cost)],
                        [quality, formatScore(p.quality)],
                        ...(pareto ? ([["Fronteira de Pareto", "sim"]] as [string, string][]) : []),
                      ]}
                    />
                  }
                />
              </g>
            );
          })}
        </svg>
        <table className="visually-hidden">
          <caption>Figura 3: {COST_LABEL[cost]} e {quality} por combinação</caption>
          <thead>
            <tr>
              <th scope="col">Posição</th>
              <th scope="col">Combinação</th>
              <th scope="col">{COST_LABEL[cost]}</th>
              <th scope="col">{quality}</th>
              <th scope="col">Fronteira de Pareto</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.key}>
                <th scope="row">#{placeOf.get(p.key) ?? "—"}</th>
                <td>{comboText(p.combo)}</td>
                <td>{formatCost(p.cost)}</td>
                <td>{formatScore(p.quality)}</td>
                <td>{onFrontier.has(p.key) ? "sim" : "não"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ChartFrame>
    </div>
  );
}
```

Depois de colar o arquivo, faça três ajustes para a tabela oculta mostrar a posição de **todas** as combinações, inclusive as fora de foco (o teste da linha `#5` depende disso):

1. Troque o import de `comboText` por `import { type RankRow, comboText } from "../../experiments/ranking";`.
2. Acrescente `ranked` ao destructuring (`points, cost, onCostChange, available, focused, ranked, metric, onShowAnswers`) e `ranked: RankRow[];` ao tipo das props.
3. Troque a linha do `placeOf` por:
   ```ts
   const placeOf = new Map(ranked.map((r, i) => [r.key, i + 1]));
   ```

- [ ] **Step 5: Ligar as figuras no `ChartsPanel`**

Em `ChartsPanel.tsx`:

1. Imports:
   ```ts
   import { useMemo, useState } from "react";
   import { Note } from "../Notice";
   import { type CostKind, costPoints, dimensionEffects, hasCost, metricLabel } from "./aggregate";
   import { CostQuality } from "./CostQuality";
   import { DimensionEffects } from "./DimensionEffects";
   ```
   (junte `costPoints`, `dimensionEffects`, `hasCost`, `metricLabel` e `type CostKind` ao import de `./aggregate` que já existe).
2. Depois do `useMemo` de `profile`:
   ```ts
   const [costChoice, setCostChoice] = useState<CostKind>("latency");
   const available = useMemo(
     () => ({ latency: hasCost(results, "latency"), tokens: hasCost(results, "tokens") }),
     [results],
   );
   const cost: CostKind | null = available[costChoice]
     ? costChoice
     : available.latency ? "latency" : available.tokens ? "tokens" : null;
   const effects = useMemo(() => dimensionEffects(results, metric), [results, metric]);
   const points = useMemo(() => (cost ? costPoints(results, cost, metric) : []), [results, cost, metric]);
   const enough = ranked.length >= 2;
   const needTwo = <Note title="Precisa de ao menos 2 combinações">Com uma combinação só não há o que comparar.</Note>;
   ```
3. Depois do `</figure>` da Figura 1:
   ```tsx
   <figure className="ditto-chart-figure">
     <figcaption className="ditto-caption">
       <strong>Figura 2.</strong> {metricLabel(metric)} por opção de cada dimensão, sobre todas as combinações. O ponto é a
       média; a barra vai da pior à melhor combinação com aquela opção. Os painéis estão ordenados pelo tamanho do efeito.
       {suffix}
     </figcaption>
     {enough ? <DimensionEffects effects={effects} metric={metric} /> : needTwo}
   </figure>

   <figure className="ditto-chart-figure">
     <figcaption className="ditto-caption">
       <strong>Figura 3.</strong> Custo × {metricLabel(metric).toLowerCase()} de todas as combinações. A linha liga a
       fronteira de Pareto: nenhuma outra combinação é ao mesmo tempo mais barata e melhor.
       {suffix}
     </figcaption>
     {!enough ? (
       needTwo
     ) : cost === null ? (
       <Note title="Sem dados de custo neste experimento">
         Ele não registrou latência nem tokens das respostas.
       </Note>
     ) : (
       <CostQuality
         points={points} cost={cost} onCostChange={setCostChoice} available={available}
         focused={focused} ranked={ranked} metric={metric} onShowAnswers={onShowAnswers}
       />
     )}
   </figure>
   ```

- [ ] **Step 6: Estilos**

Acrescente ao bloco "Charts tab" de `global.css`:

```css
.ditto-chart-panels { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px 28px; }
.ditto-chart-panel { border-top: 1.5px solid var(--ink); padding-top: 8px; }
.ditto-chart-panel-title { margin: 0 0 4px; font-size: 15px; font-weight: 650; }
.ditto-chart-panel-title .ditto-muted { font-weight: 400; font-size: 13px; margin-left: 6px; }
.ditto-chart-range { stroke: var(--line-strong); stroke-width: 2; }
.ditto-chart-dot { fill: var(--ink); }
.ditto-chart svg .ditto-chart-value, .ditto-chart-panel svg .ditto-chart-value { fill: var(--ink); font-weight: 650; }
.ditto-chart-panel svg text { font-size: 12px; fill: var(--ink-2); font-feature-settings: "tnum" 1; }
.ditto-chart-panel svg .ditto-chart-label { fill: var(--ink); font-size: 13px; }
.ditto-chart-panel .ditto-chart-axis line { stroke: var(--ink); }
.ditto-chart-panel .ditto-chart-axis .ditto-chart-grid { stroke: var(--line); }
.ditto-chart-frontier { fill: none; stroke: var(--ink); stroke-width: 1.5; stroke-dasharray: 4 3; }
.ditto-chart-ring { fill: none; stroke: var(--ink); stroke-width: 1.5; }
.ditto-chart-dot-muted { fill: var(--line-strong); }
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd frontend && npx vitest run src/components/charts && npx tsc -b`
Expected: todos PASS; `tsc` sem erros.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat(charts): dimension effects and cost-quality frontier figures"
```

---

### Task 6: Figura 4 (estabilidade por pergunta)

**Files:**
- Create: `frontend/src/components/charts/Stability.tsx`
- Modify: `frontend/src/components/charts/ChartsPanel.tsx`
- Modify: `frontend/src/components/charts/ChartsPanel.test.tsx`
- Modify: `frontend/src/pages/ExperimentDetailPage.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: Task 3 (`questionMatrix`, `quartiles`, `MatrixRow`), Task 4 (primitivas).
- Produces:
  ```ts
  export function Stability(p: {
    matrix: MatrixRow[]; focused: FocusedCombo[]; metric: string;
    onOpenRow: (row: ExperimentResultRow) => void; onShowAnswers: (combo: Combination) => void;
  }): JSX.Element;
  ```
  Rótulos: marca da 4a `#<place> mediana <x.xx>`; célula da 4b `<pergunta> · #<place>: <valor>`; célula sem resposta com `aria-label="sem resposta"`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente ao fim de `ChartsPanel.test.tsx`:

```tsx
describe("ChartsPanel · figure 4", () => {
  it("lists questions hardest first", () => {
    renderPanel({ initial: { ...DEFAULT_FOCUS, metric: "faithfulness" } });
    const table = screen.getByRole("table", { name: /figura 4b/i });
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "Pergunta difícil",
      "Pergunta fácil",
    ]);
  });

  it("clicking a cell opens that answer", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /^Pergunta difícil · #1:/ }));
    expect(onOpenRow).toHaveBeenCalledWith(
      expect.objectContaining({ question: "Pergunta difícil", chunking: "token", rag: "agentic", llm: "gemma" }),
    );
  });

  it("a distribution mark shows the combination's answers", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /^#1 mediana/ }));
    expect(onShowAnswers).toHaveBeenCalledWith(expect.objectContaining({ llm: "gemma", chunking: "token" }));
  });

  it("shows a missing answer as an empty cell", () => {
    const results = fixture().filter(
      (r) => !(r.chunking === "token" && r.rag === "agentic" && r.llm === "gemma" && r.question === "Pergunta fácil"),
    );
    renderPanel({ results });
    expect(screen.getByLabelText("sem resposta")).toBeInTheDocument();
  });

  it("shows a row without metrics as a dash, not NaN", () => {
    const results = fixture();
    const i = results.findIndex((r) => r.chunking === "token" && r.rag === "agentic" && r.llm === "gemma");
    results[i] = { ...results[i], scores: {} };
    renderPanel({ results });
    expect(document.body.innerHTML).not.toContain("NaN");
  });
});
```

Em `ExperimentDetailPage.test.tsx`, acrescente:

```tsx
  it("opens the result drawer from the charts matrix", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /gráficos/i }));
    await user.click(await screen.findByRole("button", { name: /^Pergunta A · #2:/ }));
    expect(await screen.findByText("Detalhe do resultado")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx vitest run src/components/charts/ChartsPanel.test.tsx src/pages/ExperimentDetailPage.test.tsx`
Expected: os testes novos FAIL (nenhuma tabela "figura 4b").

- [ ] **Step 3: Criar `Stability.tsx`**

```tsx
import { scaleLinear } from "d3-scale";
import { useState } from "react";

import type { ExperimentResultRow } from "../../api/types";
import type { Combination } from "../Score";
import { type FocusedCombo, type MatrixRow, metricLabel, quartiles } from "./aggregate";
import {
  AxisBottom, ChartFrame, ComboTip, GROUP_COLOR, RankMark, type Tip, formatScore, useChartWidth,
} from "./primitives";

const LABEL_W = 44;
const RIGHT = 16;
const ROW_H = 36;
const TOP = 8;
const AXIS_H = 28;

/** Deterministic vertical spread in [-5, 5] px, so dots at the same score stay visible. */
function jitter(k: number): number {
  return ((k * 7) % 11) - 5;
}

const heat = scaleLinear<string>().domain([0, 1]).range(["#fcfbf8", "#6d4bc4"]).clamp(true);

export function Stability({
  matrix, focused, metric, onOpenRow, onShowAnswers,
}: {
  matrix: MatrixRow[];
  focused: FocusedCombo[];
  metric: string;
  onOpenRow: (row: ExperimentResultRow) => void;
  onShowAnswers: (combo: Combination) => void;
}) {
  const [ref, width] = useChartWidth();
  const [tip, setTip] = useState<Tip>(null);
  const x = scaleLinear().domain([0, 1]).range([LABEL_W, width - RIGHT]);
  const bottom = TOP + focused.length * ROW_H;
  const name = metricLabel(metric);
  const columns = focused.map((f, j) => {
    const values = matrix.flatMap((r) => {
      const v = r.cells[j].value;
      return v === null ? [] : [v];
    });
    return { f, values, q: quartiles(values) };
  });

  return (
    <div className="ditto-chart-stability">
      <h4 className="ditto-chart-panel-title">a. Distribuição por combinação</h4>
      <ChartFrame frameRef={ref} tip={tip}>
        <svg width={width} height={bottom + AXIS_H} role="group" aria-label="Figura 4a: distribuição por pergunta">
          <AxisBottom scale={x} y={bottom} gridTop={TOP} />
          {columns.map(({ f, values, q }, j) => {
            const cy = TOP + j * ROW_H + ROW_H / 2;
            const color = GROUP_COLOR[f.group];
            return (
              <g key={f.row.key}>
                {q && (
                  <>
                    <rect className="ditto-chart-iqr" x={x(q.q1)} y={cy - 7} width={Math.max(1, x(q.q3) - x(q.q1))} height={14} style={{ fill: color }} />
                    <line className="ditto-chart-median" x1={x(q.median)} x2={x(q.median)} y1={cy - 10} y2={cy + 10} />
                  </>
                )}
                {values.map((v, k) => (
                  <circle key={k} className="ditto-chart-dot-soft" cx={x(v)} cy={cy + jitter(k)} r={3} style={{ fill: color }} />
                ))}
                <RankMark
                  x={LABEL_W / 2}
                  y={cy}
                  place={f.place}
                  group={f.group}
                  label={`#${f.place} mediana ${formatScore(q?.median ?? null)}`}
                  onActivate={() => onShowAnswers(f.row.combo)}
                  onTip={setTip}
                  tip={
                    <ComboTip
                      combo={f.row.combo}
                      place={f.place}
                      lines={[
                        ["Mediana", formatScore(q?.median ?? null)],
                        ["Intervalo interquartil", q ? `${formatScore(q.q1)}–${formatScore(q.q3)}` : "—"],
                        ["Perguntas", String(values.length)],
                      ]}
                    />
                  }
                />
              </g>
            );
          })}
        </svg>
      </ChartFrame>

      <h4 className="ditto-chart-panel-title">b. {name} por pergunta</h4>
      <div className="ditto-table-wrap ditto-chart-matrix-wrap">
        <table className="ditto-table ditto-chart-matrix">
          <caption className="visually-hidden">Figura 4b: {name} por pergunta e combinação</caption>
          <thead>
            <tr>
              <th scope="col">Pergunta</th>
              {focused.map((f) => (
                <th key={f.row.key} scope="col" className="ditto-num">
                  <span className="ditto-chart-col" data-group={f.group}>
                    #{f.place}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((r) => (
              <tr key={r.question}>
                <th scope="row" className="ditto-chart-question" title={r.question}>
                  {r.question}
                </th>
                {r.cells.map((c, j) => (
                  <td key={focused[j].row.key} className="ditto-chart-cell">
                    {c.row ? (
                      <button
                        type="button"
                        data-empty={c.value === null || undefined}
                        style={c.value === null ? undefined : { background: heat(c.value), color: c.value > 0.55 ? "#fff" : "var(--ink)" }}
                        aria-label={`${r.question} · #${focused[j].place}: ${formatScore(c.value)}`}
                        onClick={() => onOpenRow(c.row as ExperimentResultRow)}
                      >
                        {formatScore(c.value)}
                      </button>
                    ) : (
                      <span className="ditto-chart-cell-empty" aria-label="sem resposta">
                        —
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Ligar no `ChartsPanel`**

1. Imports: junte `questionMatrix` ao import de `./aggregate` e acrescente `import { Stability } from "./Stability";`. Acrescente `onOpenRow` ao destructuring das props do `ChartsPanel`.
2. Depois do `useMemo` de `points`:
   ```ts
   const matrix = useMemo(() => questionMatrix(results, focused, metric), [results, focused, metric]);
   ```
3. Depois do `</figure>` da Figura 3:
   ```tsx
   <figure className="ditto-chart-figure">
     <figcaption className="ditto-caption">
       <strong>Figura 4.</strong> Estabilidade das combinações em foco. Em (a), cada ponto é uma pergunta; a faixa é o
       intervalo interquartil e o traço, a mediana. Em (b), as perguntas vão da mais difícil para a mais fácil; clique
       numa célula para ler a resposta.
       {suffix}
     </figcaption>
     <Stability matrix={matrix} focused={focused} metric={metric} onOpenRow={onOpenRow} onShowAnswers={onShowAnswers} />
   </figure>
   ```

- [ ] **Step 5: Estilos**

Acrescente ao bloco "Charts tab" de `global.css`:

```css
.ditto-chart-stability { display: flex; flex-direction: column; gap: 10px; }
.ditto-chart-iqr { opacity: 0.2; }
.ditto-chart-median { stroke: var(--ink); stroke-width: 2; }
.ditto-chart-dot-soft { opacity: 0.6; }
.ditto-chart-matrix { width: auto; }
.ditto-chart-matrix td.ditto-chart-cell { padding: 2px; border-bottom: 1px solid var(--field); }
.ditto-chart-matrix th.ditto-chart-question {
  max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 400; font-size: 13px; padding: 4px 12px 4px 0; border-bottom: 1px solid var(--line);
}
.ditto-chart-cell button {
  display: block; width: 56px; height: 26px; border: 0; border-radius: 2px;
  font: inherit; font-size: 12px; font-feature-settings: "tnum" 1; cursor: pointer;
}
.ditto-chart-cell button[data-empty] {
  background: repeating-linear-gradient(45deg, var(--binder-2) 0 4px, var(--field) 4px 8px);
  color: var(--ink-3);
}
.ditto-chart-cell button:focus-visible { outline: 2px solid var(--ink); outline-offset: 1px; }
.ditto-chart-cell-empty { display: block; width: 56px; text-align: center; color: var(--ink-3); }
.ditto-chart-col { display: inline-block; min-width: 26px; padding: 1px 6px; border-radius: 10px; color: var(--ink-inverse); font-weight: 750; }
.ditto-chart-col[data-group="top"] { background: var(--hue-violet); }
.ditto-chart-col[data-group="bottom"] { background: var(--hue-orange); color: var(--ink); }
.ditto-chart-col[data-group="manual"] { background: var(--hue-ultramarine); }
```

- [ ] **Step 6: Rodar tudo**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: todos os testes do frontend PASS; `tsc` sem erros.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(charts): per-question stability figure with answer matrix"
```

---

### Task 7: Acabamento visual com impeccable e verificação no app

**Files:**
- Modify: `frontend/src/styles/global.css` (bloco "Charts tab")
- Modify: arquivos em `frontend/src/components/charts/` só onde a revisão pedir

**Interfaces:**
- Consumes: a aba completa das Tasks 4–6.
- Produces: nenhuma interface nova. Ajustes visuais que não mudam props nem os rótulos acessíveis dos testes.

- [ ] **Step 1: Subir o app**

Run: `make up-local` (na raiz do repositório). Abra `http://localhost:3000`, entre num experimento com várias combinações (de preferência a última bateria) e abra a aba **Gráficos**.

- [ ] **Step 2: Revisão com a skill impeccable**

Invoque a skill `impeccable` pedindo *critique + polish* da aba "Gráficos" contra o `DESIGN.md`, com estes critérios:
- tokens de cor e tipografia (Archivo com `tnum`, fios `--ink`/`--line`, legendas "Figura k." como a "Tabela 1." do ranking);
- contraste do texto dentro das marcas (branco sobre violeta/ultramarino, `--ink` sobre laranja) e das células do mapa;
- ritmo de espaçamento igual ao das outras abas;
- colisão de marcas na Fig. 1 quando os valores estão próximos;
- largura de 390 px: sem rolagem horizontal da página; painéis da Fig. 2 empilhados; mapa da Fig. 4b com rolagem própria.

Aplique as correções no `global.css` e, se preciso, nas constantes de layout dos componentes. Não mude os `aria-label` que os testes usam.

- [ ] **Step 3: Verificar os estados-limite no app**

No navegador, confira:
1. `Só top` → `Todas` → `Top e bottom` com N = 1 e N = 10;
2. adicionar e remover uma combinação à mão;
3. trocar a métrica dos gráficos;
4. alternar Latência/Tokens;
5. clicar numa marca (vai para "Respostas" filtrada) e numa célula (abre o drawer);
6. navegar pelas marcas com Tab e Enter.

- [ ] **Step 4: Rodar a suíte, o build e atualizar o grafo**

Run: `cd frontend && npx vitest run && npm run build && cd .. && graphify update .`
Expected: testes PASS, build sem erros, grafo atualizado.

- [ ] **Step 5: Commit**

```bash
git add frontend/src graphify-out
git commit -m "style(charts): polish charts tab against the design system"
```
