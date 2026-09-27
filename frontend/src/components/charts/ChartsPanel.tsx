import { useMemo, useState } from "react";

import type { ExperimentResultRow } from "../../api/types";
import { MEDIA_KEY, type RankRow } from "../../experiments/ranking";
import { Note } from "../Notice";
import type { Combination } from "../Score";
import {
  type CostKind, type FocusState, type Group,
  costPoints, dimensionEffects, focusSet, hasCost, metricLabel, metricProfile, questionMatrix,
} from "./aggregate";
import { CostQuality } from "./CostQuality";
import { DimensionEffects } from "./DimensionEffects";
import { FocusBar } from "./FocusBar";
import { MetricProfile } from "./MetricProfile";
import { GROUP_COLOR, GROUP_LABEL } from "./primitives";
import { Stability } from "./Stability";

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
  results, metricKeys, ranked, focus, onFocusChange, partial, onShowAnswers, onOpenRow,
}: ChartsPanelProps) {
  // A metric the experiment no longer has falls back to the média.
  const metric = focus.metric === MEDIA_KEY || metricKeys.includes(focus.metric) ? focus.metric : MEDIA_KEY;
  const effective = metric === focus.metric ? focus : { ...focus, metric };

  const focused = useMemo(() => focusSet(ranked, effective), [ranked, effective]);
  const profile = useMemo(() => metricProfile(results, focused, metricKeys), [results, focused, metricKeys]);
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
  const matrix = useMemo(() => questionMatrix(results, focused, metric), [results, focused, metric]);
  const enough = ranked.length >= 2;
  const needTwo = <Note title="Precisa de ao menos 2 combinações">Com uma combinação só não há o que comparar.</Note>;
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

      <figure className="ditto-chart-figure">
        <figcaption className="ditto-caption">
          <strong>Figura 4.</strong> Estabilidade das combinações em foco. Em (a), cada ponto é uma pergunta; a faixa é o
          intervalo interquartil e o traço, a mediana. Em (b), as perguntas vão da mais difícil para a mais fácil; clique
          numa célula para ler a resposta.
          {suffix}
        </figcaption>
        <Stability matrix={matrix} focused={focused} metric={metric} onOpenRow={onOpenRow} onShowAnswers={onShowAnswers} />
      </figure>
    </div>
  );
}
