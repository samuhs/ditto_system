import { scaleLinear } from "d3-scale";
import { type KeyboardEvent, useLayoutEffect, useRef, useState } from "react";

import type { ExperimentResultRow } from "../../api/types";
import { comboText } from "../../experiments/ranking";
import type { Combination } from "../Score";
import { type FocusedCombo, type MatrixRow, metricLabel, quartiles } from "./aggregate";
import { heat, heatText } from "./heat";
import {
  AxisBottom, ChartFrame, ComboTip, GROUP_COLOR, RankMark, formatScore, nText, useChartWidth, useTip,
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

/** Colours from the score as shown (two decimals), so equal labels get equal cells. */
function cellColors(value: number) {
  const shown = Math.round(value * 100) / 100;
  return { background: heat(shown), color: heatText(shown).css };
}

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
  // Roving tabindex in the matrix: one cell in the tab order, arrows move it.
  // The active cell is tracked by (question, combination), not by position,
  // because rows re-sort by difficulty as results come in.
  const [active, setActive] = useState<{ question: string; key: string } | null>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  // A cell of the matrix had focus; it may be replaced (empty span → button) on a re-render.
  const hadFocus = useRef(false);
  const rowCount = matrix.length;
  const colCount = focused.length;
  const activeR = active ? matrix.findIndex((r) => r.question === active.question) : -1;
  const activeC = active ? focused.findIndex((f) => f.row.key === active.key) : -1;
  const current = activeR >= 0 && activeC >= 0 ? { r: activeR, c: activeC } : { r: 0, c: 0 };
  const cellAt = (r: number, c: number) => bodyRef.current?.querySelector<HTMLElement>(`[data-cell="${r}-${c}"]`);
  const moveTo = (r: number, c: number) => {
    const next = { r: Math.max(0, Math.min(rowCount - 1, r)), c: Math.max(0, Math.min(colCount - 1, c)) };
    setActive({ question: matrix[next.r].question, key: focused[next.c].row.key });
    cellAt(next.r, next.c)?.focus();
  };
  useLayoutEffect(() => {
    // The focused cell was swapped for another element: keep focus on the active cell.
    const body = bodyRef.current;
    if (!hadFocus.current || !body || body.contains(document.activeElement)) return;
    if (document.activeElement && document.activeElement !== document.body) return;
    cellAt(current.r, current.c)?.focus();
  });
  const onCellKey = (e: KeyboardEvent, r: number, c: number) => {
    const target = {
      ArrowLeft: [r, c - 1],
      ArrowRight: [r, c + 1],
      ArrowUp: [r - 1, c],
      ArrowDown: [r + 1, c],
      Home: [r, 0],
      End: [r, colCount - 1],
    }[e.key];
    if (!target) return;
    e.preventDefault();
    moveTo(target[0], target[1]);
  };
  const x = scaleLinear().domain([0, 1]).range([LABEL_W, width - RIGHT]);
  const bottom = TOP + focused.length * ROW_H;
  const name = metricLabel(metric);
  const columns = focused.map((f, j) => {
    const values = matrix.flatMap((r) => {
      const v = r.cells[j].value;
      return v === null ? [] : [v];
    });
    // Questions in the matrix this combination has an answer for.
    const answered = matrix.filter((r) => r.cells[j].row !== null).length;
    return { f, values, answered, q: quartiles(values) };
  });
  const [tip, setTip] = useTip((key) => {
    const j = columns.findIndex((c) => c.f.row.key === key);
    if (j < 0) return null;
    const { f, q, values, answered } = columns[j];
    return {
      x: LABEL_W / 2,
      y: TOP + j * ROW_H + ROW_H / 2,
      content: (
        <ComboTip
          combo={f.row.combo}
          place={f.place}
          lines={[
            ["Mediana", formatScore(q?.median ?? null)],
            ["Intervalo interquartil", q ? `${formatScore(q.q1)}–${formatScore(q.q3)}` : "—"],
            ["Perguntas", nText(values.length, answered)],
          ]}
        />
      ),
    };
  });

  return (
    <div className="ditto-chart-stability">
      <h4 className="ditto-chart-panel-title">a. Distribuição por combinação</h4>
      <ChartFrame frameRef={ref} width={width} tip={tip}>
        <svg width={width} height={bottom + AXIS_H} role="group" aria-label="Figura 4a: distribuição por pergunta">
          <AxisBottom scale={x} y={bottom} gridTop={TOP} ticks={width < 560 ? 2 : 5} />
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
                  tipKey={f.row.key}
                />
              </g>
            );
          })}
        </svg>
        <div className="visually-hidden">
          <table>
            <caption>Figura 4a: distribuição por pergunta</caption>
            <thead>
              <tr>
                <th scope="col">Posição</th>
                <th scope="col">Combinação</th>
                <th scope="col">Mediana</th>
                <th scope="col">Q1</th>
                <th scope="col">Q3</th>
                <th scope="col">Perguntas</th>
              </tr>
            </thead>
            <tbody>
              {columns.map(({ f, values, answered, q }) => (
                <tr key={f.row.key}>
                  <th scope="row">#{f.place}</th>
                  <td>{comboText(f.row.combo)}</td>
                  <td>{formatScore(q?.median ?? null)}</td>
                  <td>{formatScore(q?.q1 ?? null)}</td>
                  <td>{formatScore(q?.q3 ?? null)}</td>
                  <td>{nText(values.length, answered)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartFrame>

      <h4 className="ditto-chart-panel-title">b. {name} por pergunta</h4>
      <div className="ditto-table-wrap ditto-chart-matrix-wrap">
        <table className="ditto-table ditto-chart-matrix">
          <caption className="visually-hidden">
            Figura 4b: {name} por pergunta e combinação. Use as setas para percorrer as células.
          </caption>
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
          <tbody ref={bodyRef}>
            {matrix.map((r, i) => (
              <tr key={r.question}>
                <th scope="row" className="ditto-chart-question" title={r.question}>
                  {r.question}
                </th>
                {r.cells.map((c, j) => {
                  const cellProps = {
                    "data-cell": `${i}-${j}`,
                    tabIndex: i === current.r && j === current.c ? 0 : -1,
                    onFocus: () => {
                      hadFocus.current = true;
                      setActive({ question: r.question, key: focused[j].row.key });
                    },
                    onBlur: () => {
                      hadFocus.current = false;
                    },
                    onKeyDown: (e: KeyboardEvent) => onCellKey(e, i, j),
                  };
                  return (
                    <td key={focused[j].row.key} className="ditto-chart-cell">
                      {c.row ? (
                        <button
                          type="button"
                          {...cellProps}
                          data-empty={c.value === null || undefined}
                          style={c.value === null ? undefined : cellColors(c.value)}
                          aria-label={`${r.question} · #${focused[j].place}: ${formatScore(c.value)}`}
                          onClick={() => onOpenRow(c.row as ExperimentResultRow)}
                        >
                          {formatScore(c.value)}
                        </button>
                      ) : (
                        <span
                          className="ditto-chart-cell-empty"
                          role="img"
                          aria-label={`${r.question} · #${focused[j].place}: sem resposta`}
                          {...cellProps}
                        >
                          <span aria-hidden="true">—</span>
                          <span className="visually-hidden">sem resposta</span>
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
