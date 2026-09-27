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
