/**
 * Colour of the figure 4b cells: a ramp from the leaf (score 0) to a dark
 * violet (score 1, the hue of --hue-violet at a lower lightness), with ink
 * text below HEAT_WHITE_FROM and white text from it.
 *
 * No continuous ramp can give every score 4.5:1 with a single ink/white
 * switch: around luminance 0.18–0.21 neither text colour reaches it (at best
 * 4.3:1). So the ramp skips that narrow band at the threshold — scores below
 * it use the light part of the ramp (up to INK_UNTIL), scores from it the dark
 * part (from WHITE_FROM) — a small, visible step that coincides with the text
 * switch. The test in heat.test.ts checks the 4.5:1 floor over 0..1.
 */
import { scaleLinear } from "d3-scale";

export const HEAT_START = "#fcfbf8"; // --leaf
/** hsl(257°, 51%, 36%): --hue-violet (#6d4bc4) darkened. */
export const HEAT_END = "#472d8a";
/** Scores from here on get white text. */
export const HEAT_WHITE_FROM = 0.68;

/** Last ramp position with ≥ 4.6:1 against ink, first with ≥ 4.6:1 against white. */
const INK_UNTIL = 0.63;
const WHITE_FROM = 0.7;

const ramp = scaleLinear<string>().domain([0, 1]).range([HEAT_START, HEAT_END]);

export function heat(v: number): string {
  const s = Math.max(0, Math.min(1, v));
  return s < HEAT_WHITE_FROM
    ? ramp((s / HEAT_WHITE_FROM) * INK_UNTIL)
    : ramp(WHITE_FROM + ((s - HEAT_WHITE_FROM) / (1 - HEAT_WHITE_FROM)) * (1 - WHITE_FROM));
}

const INK = { css: "var(--ink)", hex: "#17161a" };
const WHITE = { css: "var(--ink-inverse)", hex: "#ffffff" };

/** Text colour for a cell of score `v`: CSS token and its hex. */
export function heatText(v: number): { css: string; hex: string } {
  return v >= HEAT_WHITE_FROM ? WHITE : INK;
}
