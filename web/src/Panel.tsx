import type { Dispatch } from "react";
import { copy } from "./copy";
import { formatPath } from "./api";
import type { Action, AppState, Pin } from "./types";
import { pointInBoundary } from "./geo";

type Props = {
  state: AppState;
  dispatch: Dispatch<Action>;
  loading: boolean;
  onSearch: () => void;
  boundary: GeoJSON.GeoJSON | null;
};

export function Panel({
  state,
  dispatch,
  loading,
  onSearch,
  boundary,
}: Props) {
  const { phase, route, selected, errorMessage } = state;

  function useLocation() {
    if (!navigator.geolocation) {
      dispatch({ type: "ROUTE_ERR", message: copy.errors.server });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lon = pos.coords.longitude;
        const lat = pos.coords.latitude;
        const inBoundary = pointInBoundary(lon, lat, boundary);
        const point: Pin = { lon, lat, inBoundary };
        if (!inBoundary) {
          dispatch({ type: "ROUTE_ERR", message: copy.outsideHint });
          return;
        }
        dispatch({ type: "SET_ORIGIN", point });
      },
      () => {
        dispatch({ type: "ROUTE_ERR", message: copy.errors.server });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <section className="panel">
      <button type="button" className="location-btn" onClick={useLocation}>
        {copy.useLocation}
      </button>

      {phase === "S0" && (
        <div>
          <p>{copy.s0}</p>
          <p className="muted">{copy.s0sub}</p>
        </div>
      )}

      {phase === "S1" && (
        <div>
          <p>{copy.s1}</p>
          {state.origin && !state.origin.inBoundary && (
            <p className="muted">{copy.outsideHint}</p>
          )}
          <button
            type="button"
            onClick={() => dispatch({ type: "RESET_ORIGIN" })}
          >
            {copy.redoOrigin}
          </button>
        </div>
      )}

      {phase === "S2" && (
        <div>
          <p>{copy.s2}</p>
          {((state.origin && !state.origin.inBoundary) ||
            (state.destination && !state.destination.inBoundary)) && (
            <p className="muted">{copy.outsideHint}</p>
          )}
          <div className="row">
            <button type="button" disabled={loading} onClick={onSearch}>
              {loading ? copy.loadingRoute : copy.search}
            </button>
            <button type="button" onClick={() => dispatch({ type: "RESET" })}>
              {copy.reset}
            </button>
          </div>
        </div>
      )}

      {phase === "S3" && route && (
        <div>
          {route.same_route ? (
            <p>{copy.sameRoute}</p>
          ) : (
            <>
              <button
                type="button"
                className={
                  selected === "shortest" ? "path-card active" : "path-card"
                }
                onClick={() => dispatch({ type: "SELECT", which: "shortest" })}
              >
                <strong>{copy.legendShortest}</strong>{" "}
                {formatPath(route.shortest)}
              </button>
              {route.shadiest && (
                <button
                  type="button"
                  className={
                    selected === "shadiest" ? "path-card active" : "path-card"
                  }
                  onClick={() =>
                    dispatch({ type: "SELECT", which: "shadiest" })
                  }
                >
                  <strong>{copy.legendShade}</strong>{" "}
                  {formatPath(route.shadiest)}
                </button>
              )}
              {route.shadiest && (
                <p className="muted">
                  {copy.longer(
                    route.shadiest.distance_m - route.shortest.distance_m,
                  )}
                </p>
              )}
              {route.long_detour && <p>{copy.muchLonger}</p>}
            </>
          )}
          <button type="button" onClick={() => dispatch({ type: "RESET" })}>
            {copy.reset}
          </button>
        </div>
      )}

      {phase === "S4" && route && (
        <div>
          <p>{copy.nightOnly}</p>
          <p>
            <strong>{copy.legendShortest}</strong> {route.shortest.distance_m}m
            · {route.shortest.duration_min}分
          </p>
          <button type="button" onClick={() => dispatch({ type: "RESET" })}>
            {copy.reset}
          </button>
        </div>
      )}

      {phase === "S5" && (
        <div>
          <p>{errorMessage}</p>
          <button
            type="button"
            onClick={() => dispatch({ type: "CLEAR_ERROR" })}
          >
            {copy.close}
          </button>
        </div>
      )}

      <p className="attribution">{copy.attribution}</p>
    </section>
  );
}
