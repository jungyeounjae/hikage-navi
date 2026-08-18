import { describe, expect, it } from "vitest";
import {
  formatContinuousSun,
  formatPath,
  localInputToIso,
  shadowsQuery,
  waterPopupHtml,
  waterPopupLines,
} from "./api";
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

  it("waterPopupLines omits missing optional fields", () => {
    const lines = waterPopupLines({
      id: "osm-near",
      name: null,
      lat: 35.658,
      lon: 139.7016,
      type: "DRINKING_WATER",
      source: "OSM",
      bottle_refill: null,
      access: null,
      opening_hours: null,
      route_distance_m: 28,
    });
    expect(lines).toEqual([
      "給水スポット",
      "💧 給水可能",
      "ルートから約28m",
    ]);
    expect(lines.join("\n")).not.toContain("利用時間");
    expect(lines.join("\n")).not.toContain("マイボトル");
  });

  it("waterPopupLines includes optional fields when present", () => {
    const lines = waterPopupLines({
      id: "osm-named",
      name: "代々木公園",
      lat: 35.671,
      lon: 139.695,
      type: "DRINKING_WATER",
      source: "OSM",
      bottle_refill: true,
      access: "yes",
      opening_hours: "9:00〜18:00",
      route_distance_m: 30,
    });
    expect(lines).toEqual([
      "代々木公園",
      "💧 給水可能",
      "ルートから約30m",
      "マイボトル給水可能",
      "yes",
      "利用時間 9:00〜18:00",
    ]);
  });

  it("waterPopupHtml escapes < and & before setHTML join", () => {
    const html = waterPopupHtml({
      id: "osm-xss",
      name: '<img src=x onerror=alert(1)> & more',
      lat: 35.658,
      lon: 139.7016,
      type: "DRINKING_WATER",
      source: "OSM",
      bottle_refill: null,
      access: "yes & public",
      opening_hours: "9:00<script>",
      route_distance_m: 28,
    });
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("& more");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt; &amp; more");
    expect(html).toContain("yes &amp; public");
    expect(html).toContain("利用時間 9:00&lt;script&gt;");
    expect(html).toContain("<br>");
  });
});
