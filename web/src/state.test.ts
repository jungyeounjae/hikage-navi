import { describe, expect, it } from "vitest";
import { initialState, reduce } from "./state";
import type { PathDto, RouteResponse, WaterSpotDto } from "./types";

const origin = { lon: 139.7016, lat: 35.658, inBoundary: true };
const dest = { lon: 139.7027, lat: 35.657, inBoundary: true };

function waterSpot(over: Partial<WaterSpotDto> = {}): WaterSpotDto {
  return {
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
    ...over,
  };
}

function pathDto(over: Partial<PathDto> = {}): PathDto {
  return {
    coordinates: [[139.7016, 35.658]],
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

function nightlessRoute(): RouteResponse {
  return {
    night: false,
    same_route: false,
    long_detour: false,
    warning: null,
    shortest: pathDto({
      water_spots: [waterSpot({ id: "short-water", lon: 139.701, lat: 35.658 })],
    }),
    shadiest: pathDto({
      distance_m: 1300,
      shade_pct: 40,
      water_spots: [waterSpot({ id: "shade-water", lon: 139.703, lat: 35.657 })],
    }),
  };
}

describe("map tap", () => {
  it("S0 tap sets origin and S1", () => {
    const s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    expect(s.phase).toBe("S1");
    expect(s.origin).toEqual(origin);
  });

  it("S1 tap sets destination and S2", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    expect(s.phase).toBe("S2");
    expect(s.destination).toEqual(dest);
  });

  it("reset returns S0", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "RESET" });
    expect(s.phase).toBe("S0");
    expect(s.origin).toBeNull();
  });
});

describe("water toggle", () => {
  it("starts with waterVisible true", () => {
    expect(initialState().waterVisible).toBe(true);
  });

  it("TOGGLE_WATER flips waterVisible without clearing the route", () => {
    const withRoute = reduce(initialState(), {
      type: "ROUTE_OK",
      route: nightlessRoute(),
    });
    const off = reduce(withRoute, { type: "TOGGLE_WATER" });
    expect(off.waterVisible).toBe(false);
    expect(off.route).toBe(withRoute.route);
    expect(reduce(off, { type: "TOGGLE_WATER" }).waterVisible).toBe(true);
  });

  it("SELECT changes selected without dropping the route or water spots", () => {
    const withRoute = reduce(initialState(), {
      type: "ROUTE_OK",
      route: nightlessRoute(),
    });
    expect(withRoute.selected).toBe("shadiest");
    const next = reduce(withRoute, { type: "SELECT", which: "shortest" });
    expect(next.selected).toBe("shortest");
    expect(next.route).toBe(withRoute.route);
    expect(next.route?.shortest.water_spots[0]?.id).toBe("short-water");
    expect(next.waterVisible).toBe(true);
  });

  it("RESET restores waterVisible to true", () => {
    const withRoute = reduce(initialState(), {
      type: "ROUTE_OK",
      route: nightlessRoute(),
    });
    const off = reduce(withRoute, { type: "TOGGLE_WATER" });
    expect(reduce(off, { type: "RESET" }).waterVisible).toBe(true);
  });
});
