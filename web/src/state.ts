import type { Action, AppState } from "./types";

function nowLocalInput(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function initialState(): AppState {
  return {
    phase: "S0",
    origin: null,
    destination: null,
    datetimeLocal: nowLocalInput(),
    route: null,
    errorMessage: null,
    selected: "shadiest",
  };
}

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "MAP_TAP": {
      if (state.phase === "S0" || (state.phase === "S1" && !state.origin)) {
        return {
          ...state,
          origin: action.point,
          destination: null,
          route: null,
          phase: "S1",
          errorMessage: null,
        };
      }
      if (state.phase === "S1") {
        return {
          ...state,
          destination: action.point,
          route: null,
          phase: "S2",
          errorMessage: null,
        };
      }
      return {
        ...state,
        destination: action.point,
        route: null,
        phase: "S2",
        errorMessage: null,
      };
    }
    case "SET_ORIGIN":
      return {
        ...state,
        origin: action.point,
        phase: state.destination ? "S2" : "S1",
        route: null,
        errorMessage: null,
      };
    case "RESET":
      return { ...initialState(), datetimeLocal: state.datetimeLocal };
    case "RESET_ORIGIN":
      return {
        ...state,
        origin: null,
        destination: null,
        route: null,
        phase: "S0",
        errorMessage: null,
      };
    case "SET_DATETIME":
      return { ...state, datetimeLocal: action.value };
    case "ROUTE_OK": {
      const night = action.route.night;
      const selected =
        night || action.route.same_route ? "shortest" : "shadiest";
      return {
        ...state,
        route: action.route,
        phase: night ? "S4" : "S3",
        selected,
        errorMessage: null,
      };
    }
    case "ROUTE_ERR":
      return {
        ...state,
        phase: "S5",
        errorMessage: action.message,
        route: null,
      };
    case "CLEAR_ERROR":
      return {
        ...state,
        phase: state.destination ? "S2" : state.origin ? "S1" : "S0",
        errorMessage: null,
      };
    case "SELECT":
      return { ...state, selected: action.which };
    default:
      return state;
  }
}
