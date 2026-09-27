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
