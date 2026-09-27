import { scaleLinear } from "d3-scale";
import { Fragment } from "react";

import { dimName } from "../../experiments/ranking";
import { DIM_LABEL, type DimensionEffects as Effects, metricLabel } from "./aggregate";
import { AxisBottom, ChartFrame, formatScore, useChartWidth, useTip } from "./primitives";

const PANEL_W = 360;
const LABEL_W = 130;
const VALUE_W = 44;
const ROW_H = 26;
const PAD = 6;
const AXIS_H = 22;

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

type Effect = Effects["varying"][number];
type Option = Effect["options"][number];

function optionLabel(d: Effect, o: Option): string {
  return (
    `${DIM_LABEL[d.dim]} ${dimName(d.dim, o.option)}: média ${formatScore(o.mean)}, ` +
    `de ${formatScore(o.min)} a ${formatScore(o.max)}, ${o.combos} ${o.combos === 1 ? "combinação" : "combinações"}`
  );
}

function OptionTip({ d, o }: { d: Effect; o: Option }) {
  const lines: [string, string][] = [
    ["Média", formatScore(o.mean)],
    ["Da pior à melhor", `${formatScore(o.min)}–${formatScore(o.max)}`],
    ["Combinações", String(o.combos)],
  ];
  return (
    <>
      <div className="ditto-chart-tip-title">
        {DIM_LABEL[d.dim]}: {dimName(d.dim, o.option)}
      </div>
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

/** One dimension's panel, drawn at its real width so the text keeps its size. */
function EffectPanel({ dim: d }: { dim: Effect }) {
  const [ref, width] = useChartWidth(PANEL_W);
  const x = scaleLinear().domain([0, 1]).range([LABEL_W, Math.max(LABEL_W + 80, width - VALUE_W)]);
  const bottom = PAD + d.options.length * ROW_H;
  const [tip, setTip] = useTip((key) => {
    const i = d.options.findIndex((o) => o.option === key);
    if (i < 0) return null;
    return { x: x(d.options[i].mean), y: PAD + i * ROW_H + ROW_H / 2, content: <OptionTip d={d} o={d.options[i]} /> };
  });
  return (
    <section className="ditto-chart-panel" aria-label={`${DIM_LABEL[d.dim]}: efeito ${formatScore(d.effect)}`}>
      <h4 className="ditto-chart-panel-title">
        {DIM_LABEL[d.dim]} <span className="ditto-muted">efeito {formatScore(d.effect)}</span>
      </h4>
      <ChartFrame frameRef={ref} width={width} tip={tip}>
        <svg width={width} height={bottom + AXIS_H}>
          {d.options.map((o, i) => {
            const cy = PAD + i * ROW_H + ROW_H / 2;
            const name = dimName(d.dim, o.option);
            const show = () => setTip(o.option);
            const hide = () => setTip(null);
            return (
              <g
                key={o.option}
                className="ditto-chart-option"
                role="img"
                tabIndex={0}
                aria-label={optionLabel(d, o)}
                onMouseEnter={show}
                onMouseLeave={hide}
                onFocus={show}
                onBlur={hide}
              >
                <rect className="ditto-chart-hit" x={0} y={cy - ROW_H / 2} width={width} height={ROW_H} />
                <text x={LABEL_W - 8} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-label">
                  {clip(name, 18)}
                </text>
                <line className="ditto-chart-range" x1={x(o.min)} x2={x(o.max)} y1={cy} y2={cy} />
                <circle className="ditto-chart-dot" cx={x(o.mean)} cy={cy} r={5} />
                <text x={width - 4} y={cy} dy="0.35em" textAnchor="end" className="ditto-chart-value">
                  {formatScore(o.mean)}
                </text>
              </g>
            );
          })}
          <AxisBottom scale={x} y={bottom} ticks={2} gridTop={PAD} />
        </svg>
      </ChartFrame>
    </section>
  );
}

export function DimensionEffects({ effects, metric }: { effects: Effects; metric: string }) {
  if (effects.varying.length === 0 && effects.fixed.length === 0 && effects.pending.length === 0) {
    return <p className="ditto-caption">Sem dados suficientes para comparar as dimensões.</p>;
  }
  return (
    <div>
      {effects.varying.length > 0 && (
        <div className="ditto-chart-panels">
          {effects.varying.map((d) => (
            <EffectPanel key={d.dim} dim={d} />
          ))}
        </div>
      )}
      {effects.fixed.length > 0 && (
        <p className="ditto-caption">
          Fixo neste experimento:{" "}
          {effects.fixed.map((f) => `${DIM_LABEL[f.dim]} ${dimName(f.dim, f.option)}`).join(", ")}.
        </p>
      )}
      {effects.pending.length > 0 && (
        <p className="ditto-caption">
          Sem dados suficientes ainda: {effects.pending.map((d) => DIM_LABEL[d]).join(", ")}.
        </p>
      )}
      {effects.incompleteGrid && effects.varying.length > 0 && (
        <p className="ditto-caption">
          <strong>Grade incompleta:</strong> o efeito de uma dimensão pode se misturar com o das outras.
        </p>
      )}
      <div className="visually-hidden">
        <table>
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
    </div>
  );
}
