import { describe, expect, it } from "vitest";

import { formatDuration } from "./duration";

describe("formatDuration", () => {
  it("formats seconds only", () => expect(formatDuration(45000)).toBe("45s"));
  it("formats minutes and seconds", () => expect(formatDuration(130000)).toBe("2m 10s"));
  it("formats hours, minutes and seconds", () => expect(formatDuration(5025000)).toBe("1h 23m 45s"));
  it("clamps zero and negatives", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(-100)).toBe("0s");
  });
});
