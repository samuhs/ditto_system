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
