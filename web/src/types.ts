export type Phase = "S0" | "S1" | "S2" | "S3" | "S4" | "S5";

export type Pin = { lon: number; lat: number; inBoundary: boolean };

export type PathDto = {
  coordinates: [number, number][];
  distance_m: number;
  duration_min: number;
  shade_m: number;
  sun_m: number;
  shade_pct: number;
};

export type RouteResponse = {
  night: boolean;
  shortest: PathDto;
  shadiest: PathDto | null;
  same_route: boolean;
  long_detour: boolean;
  warning: string | null;
};

export type AppState = {
  phase: Phase;
  origin: Pin | null;
  destination: Pin | null;
  datetimeLocal: string;
  route: RouteResponse | null;
  errorMessage: string | null;
  selected: "shortest" | "shadiest";
};

export type Action =
  | { type: "MAP_TAP"; point: Pin }
  | { type: "RESET" }
  | { type: "RESET_ORIGIN" }
  | { type: "SET_DATETIME"; value: string }
  | { type: "ROUTE_OK"; route: RouteResponse }
  | { type: "ROUTE_ERR"; message: string }
  | { type: "CLEAR_ERROR" }
  | { type: "SELECT"; which: "shortest" | "shadiest" }
  | { type: "SET_ORIGIN"; point: Pin };
