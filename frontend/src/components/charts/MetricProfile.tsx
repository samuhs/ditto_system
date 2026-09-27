import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { MEDIA_KEY } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { type Group, type ProfileLine, metricLabel } from "./aggregate";
import {
  AxisBottom, ChartFrame, ComboTip, MARK_R, RankMark, type TipAnchor, formatGap, formatScore, nText, useChartWidth,
} from "./primitives";

const TOP = 8;
const AXIS_H = 28;
/** Vertical distance between stacked marks: they may overlap a little, the numbers never do. */
const LANE_STEP = 16;
const MIN_ROW_H = 40;

/**
 * Vertical offsets that keep marks of the same row from covering each other.
 * Top marks stack upwards, bottom and manual ones downwards (a single side
 * spreads around the line). A mark keeps its x; it only moves to the first
 * free lane, and past the last lane it shares the least crowded one.
 */
function dodge(lines: ProfileLine[], x: (v: number) => number) {
  const sideOf = (g: Group) => (g === "top" ? "up" : "down");
  const sides = new Set(lines.flatMap((l) => l.points.map((p) => sideOf(p.combo.group))));
  const single = sides.size < 2;
  const laneOffsets = {
    up: single ? [0, -LANE_STEP, LANE_STEP, -2 * LANE_STEP, 2 * LANE_STEP] : [-8, -8 - LANE_STEP, -8 - 2 * LANE_STEP],
    down: single ? [0, -LANE_STEP, LANE_STEP, -2 * LANE_STEP, 2 * LANE_STEP] : [8, 8 + LANE_STEP, 8 + 2 * LANE_STEP],
  };
  const offsets = lines.map((line) => {
    const out = new Map<string, number>();
    for (const side of ["up", "down"] as const) {
      const pts = line.points
        .filter((p) => p.value !== null && sideOf(p.combo.group) === side)
        .map((p) => ({ key: p.combo.row.key, px: x(p.value as number) }))
        .sort((a, b) => a.px - b.px);
      const lanes = laneOffsets[side];
      const lastX = lanes.map(() => -Infinity);
      for (const p of pts) {
        let lane = lastX.findIndex((lx) => p.px - lx >= 2 * MARK_R + 1);
        if (lane < 0) lane = lastX.indexOf(Math.min(...lastX));
        lastX[lane] = p.px;
        out.set(p.key, lanes[lane]);
      }
    }
    return out;
  });
  // Each row is as tall as its own stack; the line sits between the two sides.
  let top = TOP;
  const rows = offsets.map((m) => {
    const values = [...m.values()];
    const up = Math.max(0, ...values.map((v) => -v));
    const down = Math.max(0, ...values);
    const h = Math.max(MIN_ROW_H, up + down + 2 * MARK_R + 12);
    const cy = top + (h - up - down) / 2 + up;
    top += h;
    return { offsets: m, cy, h };
  });
  return { rows, bottom: top };
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function MetricProfile({
  lines, showGap, onShowAnswers,
}: {
  lines: ProfileLine[];
  showGap: boolean;
  onShowAnswers: (combo: Combination) => void;
}) {
  const [ref, width] = useChartWidth();
  const [tip, setTip] = useState<TipAnchor>(null);
  const narrow = width < 560;
  const labelW = narrow ? 118 : 184;
  const gapW = narrow ? 48 : 64;
  const x = scaleLinear().domain([0, 1]).range([labelW, Math.max(labelW + 120, width - gapW)]);
  const { rows, bottom } = dodge(lines, x);
  const combos = lines[0]?.points.map((p) => p.combo) ?? [];
  const tipKey = (metric: string, comboKey: string) => `${metric}|${comboKey}`;
  const tipContent = (() => {
    if (!tip) return null;
    for (const line of lines) {
      for (const p of line.points) {
        if (p.value === null || tipKey(line.metric, p.combo.row.key) !== tip.key) continue;
        return (
          <ComboTip
            combo={p.combo.row.combo}
            place={p.combo.place}
            lines={[[metricLabel(line.metric), formatScore(p.value)], ["Perguntas", nText(p.n, p.total)]]}
          />
        );
      }
    }
    return null;
  })();

  return (
    <ChartFrame frameRef={ref} width={width} tip={tip} content={tipContent}>
      <svg width={width} height={bottom + AXIS_H} role="group" aria-label="Figura 1: perfil de métricas">
        <AxisBottom scale={x} y={bottom} gridTop={TOP} ticks={narrow ? 2 : 5} />
        {lines.map((line, i) => {
          const { cy, offsets } = rows[i];
          const name = metricLabel(line.metric);
          return (
            <g key={line.metric} className="ditto-chart-row" data-media={line.metric === MEDIA_KEY || undefined}>
              <text x={labelW - 12} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-label">
                {narrow ? clip(name, 15) : name}
                {narrow && name.length > 15 && <title>{name}</title>}
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
                    y={cy + (offsets.get(p.combo.row.key) ?? 0)}
                    place={p.combo.place}
                    group={p.combo.group}
                    label={`#${p.combo.place} ${name} ${formatScore(p.value)}`}
                    onActivate={() => onShowAnswers(p.combo.row.combo)}
                    onTip={setTip}
                    tipKey={tipKey(line.metric, p.combo.row.key)}
                  />
                ),
              )}
            </g>
          );
        })}
      </svg>
      <div className="visually-hidden">
        <table>
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
      </div>
    </ChartFrame>
  );
}
