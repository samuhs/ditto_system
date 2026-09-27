import { describe, expect, it } from "vitest";

import type { FocusedCombo, Group, ProfileLine } from "./aggregate";
import { dodge } from "./MetricProfile";
import { MARK_R } from "./primitives";

function line(groups: Group[]): ProfileLine {
  const points = groups.map((group, i) => ({
    combo: { row: { key: `c${i}` }, place: i + 1, group } as unknown as FocusedCombo,
    value: 0.5 + i * 0.0005, // nearly equal x: every mark collides with every other
    n: 1,
    total: 1,
  }));
  return { metric: "m", points, topMean: null, bottomMean: null, gap: null };
}

const x = (v: number) => v * 600;

/** Within a lane (same offset), marks are at least a disc apart horizontally. */
function expectNoOverlap(l: ProfileLine, offsets: Map<string, number>) {
  const lanes = new Map<number, number[]>();
  for (const p of l.points) {
    const off = offsets.get(p.combo.row.key) as number;
    expect(off).toBeDefined();
    lanes.set(off, [...(lanes.get(off) ?? []), x(p.value as number)]);
  }
  for (const xs of lanes.values()) {
    xs.sort((a, b) => a - b);
    for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(2 * MARK_R);
  }
}

describe("dodge", () => {
  it("gives each of 20 colliding marks on one side a lane of its own", () => {
    const l = line(Array<Group>(20).fill("top"));
    const { rows } = dodge([l], x);
    expectNoOverlap(l, rows[0].offsets);
    expect(new Set(rows[0].offsets.values()).size).toBe(20);
  });

  it("does the same with top and bottom marks, and the row grows to fit", () => {
    const l = line([...Array<Group>(10).fill("top"), ...Array<Group>(10).fill("bottom")]);
    const { rows } = dodge([l], x);
    expectNoOverlap(l, rows[0].offsets);
    const offsets = [...rows[0].offsets.values()];
    expect(rows[0].h).toBeGreaterThanOrEqual(Math.max(...offsets) - Math.min(...offsets) + 2 * MARK_R);
  });

  it("keeps a row compact when marks do not collide", () => {
    const l = line(["top", "bottom"]);
    l.points[1].value = 0.9;
    expect(dodge([l], x).rows[0].h).toBeLessThanOrEqual(56);
  });
});
