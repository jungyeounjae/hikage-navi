import { describe, expect, it } from "vitest";
import { formatPath, localInputToIso, shadowsQuery } from "./api";
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
