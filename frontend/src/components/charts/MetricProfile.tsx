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
