import { SegmentedControl } from "@mantine/core";
import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { type RankRow, comboText } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { COST_LABEL, type CostKind, type CostPoint, type FocusedCombo, metricLabel, paretoFrontier } from "./aggregate";
import { AxisBottom, AxisLeft, ChartFrame, ComboTip, RankMark, type TipAnchor, formatScore, useChartWidth } from "./primitives";

const M = { top: 12, right: 24, bottom: 44, left: 52 };
const H = 320;

function formatCost(v: number): string {
  return Math.round(v).toLocaleString("pt-BR");
}

export function CostQuality({
  points, cost, onCostChange, available, focused, ranked, metric, onShowAnswers,
}: {
  points: CostPoint[];
  cost: CostKind;
  onCostChange: (c: CostKind) => void;
  available: Record<CostKind, boolean>;
  focused: FocusedCombo[];
  ranked: RankRow[];
  metric: string;
  onShowAnswers: (combo: Combination) => void;
}) {
  const [ref, width] = useChartWidth();
  const [tip, setTip] = useState<TipAnchor>(null);
  const frontier = paretoFrontier(points);
  const onFrontier = new Set(frontier.map((p) => p.key));
  const byKey = new Map(focused.map((f) => [f.row.key, f]));
  const placeOf = new Map(ranked.map((r, i) => [r.key, i + 1]));

  const maxCost = Math.max(...points.map((p) => p.cost), 1);
  const x = scaleLinear().domain([0, maxCost]).nice().range([M.left, width - M.right]);
  const y = scaleLinear().domain([0, 1]).range([H - M.bottom, M.top]);
  const path = frontier
    .map((p, i) => (i === 0 ? `M${x(p.cost)},${y(p.quality)}` : `H${x(p.cost)}V${y(p.quality)}`))
    .join("");
  const muted = points.filter((p) => !byKey.has(p.key));
  const marked = points.filter((p) => byKey.has(p.key));
  const quality = metricLabel(metric);
  const tipPoint = tip ? marked.find((p) => p.key === tip.key) : undefined;
  const tipContent = tipPoint ? (
    <ComboTip
      combo={tipPoint.combo}
      place={(byKey.get(tipPoint.key) as FocusedCombo).place}
      lines={[
        [COST_LABEL[cost], formatCost(tipPoint.cost)],
        [quality, formatScore(tipPoint.quality)],
        ...(onFrontier.has(tipPoint.key) ? ([["Fronteira de Pareto", "sim"]] as [string, string][]) : []),
      ]}
    />
  ) : null;

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
      <ChartFrame frameRef={ref} width={width} tip={tip} content={tipContent}>
        <svg width={width} height={H} role="group" aria-label="Figura 3: custo e qualidade">
          <AxisLeft scale={y} x={M.left} gridRight={width - M.right} />
          <AxisBottom scale={x} y={H - M.bottom} format={formatCost} ticks={width < 560 ? 3 : 5} />
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
                  tipKey={p.key}
                />
              </g>
            );
          })}
        </svg>
        <div className="visually-hidden">
          <table>
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
        </div>
      </ChartFrame>
    </div>
  );
}
