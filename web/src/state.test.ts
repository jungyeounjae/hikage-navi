import { describe, expect, it } from "vitest";
import { initialState, reduce } from "./state";

const origin = { lon: 139.7016, lat: 35.658, inBoundary: true };
const dest = { lon: 139.7027, lat: 35.657, inBoundary: true };

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
