import { describe, expect, it } from "vitest";
import { copy } from "./copy";
import { formatPath } from "./api";
import {
  advanceSheetSnap,
  clampShadePct,
  peekHeadline,
  selectedPath,
  sheetAfterMapTap,
} from "./sheet";
import { initialState, reduce } from "./state";
import type { PathDto, RouteResponse } from "./types";

const origin = { lon: 139.7016, lat: 35.658, inBoundary: true };
const dest = { lon: 139.7027, lat: 35.657, inBoundary: true };

function path(over: Partial<PathDto> = {}): PathDto {
  return {
    coordinates: [],
    distance_m: 315,
    duration_min: 4,
    shade_m: 120,
    sun_m: 195,
    shade_pct: 80,
    max_continuous_sun_m: 24,
    max_continuous_sun_seconds: 18,
    water_spots: [],
    ...over,
  };
}

function dayRoute(): RouteResponse {
  return {
    night: false,
    same_route: false,
    long_detour: false,
    warning: null,
    shortest: path({ shade_pct: 39, distance_m: 315 }),
    shadiest: path({ shade_pct: 80, distance_m: 316 }),
  };
}

describe("peekHeadline", () => {
  it("shows loading over any phase", () => {
    expect(peekHeadline(initialState(), true)).toBe(copy.loadingRoute);
  });

  it("S0 uses s0", () => {
    expect(peekHeadline(initialState(), false)).toBe(copy.s0);
  });

  it("S1 uses peekS1", () => {
    const s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    expect(peekHeadline(s, false)).toBe(copy.peekS1);
  });

  it("S3 uses selected path label and formatPath", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    s = reduce(s, { type: "ROUTE_OK", route: dayRoute() });
    expect(s.selected).toBe("shadiest");
    expect(peekHeadline(s, false)).toBe(
      `${copy.legendShade} ${formatPath(dayRoute().shadiest!)}`,
    );
  });

  it("S4 is night shortest without shade pct", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    const night = {
      ...dayRoute(),
      night: true,
      shadiest: null,
      shortest: path({ distance_m: 315, duration_min: 4 }),
    };
    s = reduce(s, { type: "ROUTE_OK", route: night });
    expect(peekHeadline(s, false)).toBe("夜間 · 最短 315m · 4分");
  });
});

describe("selectedPath", () => {
  it("returns shadiest when selected", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    s = reduce(s, { type: "ROUTE_OK", route: dayRoute() });
    expect(selectedPath(s)?.shade_pct).toBe(80);
  });
});

describe("sheet snap", () => {
  it("cycles peek → half → expanded → peek", () => {
    expect(advanceSheetSnap("peek")).toBe("half");
    expect(advanceSheetSnap("half")).toBe("expanded");
    expect(advanceSheetSnap("expanded")).toBe("peek");
  });

  it("map tap collapses to peek", () => {
    expect(sheetAfterMapTap()).toBe("peek");
  });
});

describe("clampShadePct", () => {
  it("clamps to 0–100 integers", () => {
    expect(clampShadePct(-3)).toBe(0);
    expect(clampShadePct(80.4)).toBe(80);
    expect(clampShadePct(150)).toBe(100);
    expect(clampShadePct(Number.NaN)).toBe(0);
  });
});
