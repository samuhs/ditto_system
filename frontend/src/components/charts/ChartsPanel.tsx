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
