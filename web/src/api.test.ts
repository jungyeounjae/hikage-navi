import { describe, expect, it } from "vitest";
import { formatPath, localInputToIso } from "./api";
import type { PathDto } from "./types";

describe("api helpers", () => {
  it("localInputToIso appends seconds and JST offset", () => {
    expect(localInputToIso("2026-08-14T12:00")).toBe(
      "2026-08-14T12:00:00+09:00",
    );
  });

  it("formatPath shows distance, minutes, shade pct", () => {
    const p: PathDto = {
      coordinates: [],
      distance_m: 1200,
      duration_min: 15,
      shade_m: 240,
      sun_m: 960,
      shade_pct: 20,
    };
    expect(formatPath(p)).toBe("1200m · 15分 · 日陰 20%");
  });
});
