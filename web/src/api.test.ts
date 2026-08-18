import { describe, expect, it } from "vitest";
import { formatContinuousSun, formatPath, localInputToIso, shadowsQuery } from "./api";
import type { PathDto } from "./types";

function samplePath(over: Partial<PathDto> = {}): PathDto {
  return {
    coordinates: [],
    distance_m: 1200,
    duration_min: 15,
    shade_m: 240,
    sun_m: 960,
    shade_pct: 20,
    max_continuous_sun_m: 24,
    max_continuous_sun_seconds: 18,
    water_spots: [],
    ...over,
  };
}

describe("api helpers", () => {
  it("localInputToIso appends seconds and JST offset", () => {
    expect(localInputToIso("2026-08-14T12:00")).toBe(
      "2026-08-14T12:00:00+09:00",
    );
  });

  it("formatPath shows distance, minutes, shade pct", () => {
    expect(formatPath(samplePath())).toBe("1200m · 15分 · 日陰 20%");
  });

  it("formatContinuousSun shows max seconds", () => {
    expect(formatContinuousSun(samplePath())).toBe("連続直射日光 最大18秒");
  });

  it("formatContinuousSun uses minutes when >= 60 seconds", () => {
    expect(
      formatContinuousSun(samplePath({ max_continuous_sun_seconds: 135 })),
    ).toBe("連続直射日光 最大2分15秒");
  });

  it("formatContinuousSun omits leftover seconds at whole minutes", () => {
    expect(
      formatContinuousSun(samplePath({ max_continuous_sun_seconds: 120 })),
    ).toBe("連続直射日光 最大2分");
  });

  it("shadowsQuery omits bbox when the viewport is unknown", () => {
    expect(shadowsQuery("2026-08-14T12:00:00+09:00")).toBe(
      "datetime=2026-08-14T12%3A00%3A00%2B09%3A00",
    );
  });

  it("shadowsQuery sends the viewport as minLon,minLat,maxLon,maxLat", () => {
    const q = shadowsQuery("2026-08-14T12:00:00+09:00", [
      139.69511, 35.65312, 139.71234, 35.66456,
    ]);
    expect(new URLSearchParams(q).get("bbox")).toBe(
      "139.6951,35.6531,139.7123,35.6646",
    );
  });
});
