import { describe, expect, it } from "vitest";

import { HEAT_END, HEAT_WHITE_FROM, heat, heatText } from "./heat";

/** WCAG 2 relative luminance of "#rrggbb" or "rgb(r, g, b)". */
function luminance(color: string): number {
  const channels = color.startsWith("#")
    ? [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16))
    : (color.match(/\d+(\.\d+)?/g) ?? []).slice(0, 3).map(Number);
  expect(channels).toHaveLength(3);
  const [r, g, b] = channels.map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("heat ramp", () => {
  it("gives every score from 0 to 1 at least 4.5:1 between the cell and its text", () => {
    let min = Infinity;
    // 0.001 steps include every 0.01 step; the extra samples guard the threshold.
    const samples = [...Array.from({ length: 1001 }, (_, i) => i / 1000), HEAT_WHITE_FROM - 1e-9, HEAT_WHITE_FROM];
    for (const v of samples) {
      const ratio = contrast(heat(v), heatText(v).hex);
      min = Math.min(min, ratio);
      expect(ratio, `score ${v}`).toBeGreaterThanOrEqual(4.5);
    }
    expect(min).toBeGreaterThanOrEqual(4.5);
  });

  it("switches from ink to white once, at the threshold", () => {
    expect(heatText(HEAT_WHITE_FROM - 0.01).hex).toBe("#17161a");
    expect(heatText(HEAT_WHITE_FROM).hex).toBe("#ffffff");
    expect(heatText(1).css).toBe("var(--ink-inverse)");
    expect(heatText(0).css).toBe("var(--ink)");
  });

  it("runs from the leaf to the darker violet and clamps outside 0..1", () => {
    expect(luminance(heat(0))).toBeCloseTo(luminance("#fcfbf8"), 5);
    expect(luminance(heat(1))).toBeCloseTo(luminance(HEAT_END), 5);
    expect(heat(1.2)).toBe(heat(1));
    expect(heat(-0.1)).toBe(heat(0));
    expect(luminance(HEAT_END)).toBeLessThan(luminance("#6d4bc4"));
  });

  it("gets darker as the score grows", () => {
    for (let i = 1; i <= 100; i++) expect(luminance(heat(i / 100))).toBeLessThan(luminance(heat((i - 1) / 100)));
  });
});
