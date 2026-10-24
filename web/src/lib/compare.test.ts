import { describe, expect, it } from "vitest";
import { formatDuration, summarizeDeltas } from "./compare";

describe("summarizeDeltas", () => {
  it("reports no differences for empty or unchanged-only counts", () => {
    expect(summarizeDeltas({})).toBe("No differences");
    expect(summarizeDeltas({ unchanged: 4 })).toBe("No differences");
  });
  it("lists regressions first, then improvements, new and removed", () => {
    expect(summarizeDeltas({ improved: 2, regressed: 1, added: 3, removed: 1, unchanged: 9 })).toBe(
      "1 regressed · 2 improved · 3 new · 1 removed",
    );
  });
});

describe("formatDuration", () => {
  it("formats ms, seconds and minutes", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(412)).toBe("412 ms");
    expect(formatDuration(6240)).toBe("6.2 s");
    expect(formatDuration(125_000)).toBe("2 m 5 s");
  });
});
