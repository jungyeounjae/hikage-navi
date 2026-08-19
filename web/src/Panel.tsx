import { useEffect, useRef, type Dispatch } from "react";
import { animate } from "animejs";
import { copy } from "./copy";
import { formatContinuousSun, formatPath } from "./api";
import type { Action, AppState, Pin } from "./types";
import { pointInBoundary } from "./geo";
import { ShadeRing } from "./ShadeRing";
import {
  peekHeadline,
  sheetHeightVar,
  showPeekSearch,
  type SheetSnap,
} from "./sheet";

type Props = {
  state: AppState;
  dispatch: Dispatch<Action>;
  loading: boolean;
  onSearch: () => void;
  snap: SheetSnap;
  onAdvanceSnap: () => void;
};

export function LocationFab({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="location-fab" onClick={onClick}>
      {copy.useLocation}
    </button>
  );
}

export function createLocateHandler(
  dispatch: Dispatch<Action>,
  boundary: GeoJSON.GeoJSON | null,
) {
  return function locate() {
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
  };
}

export function Panel({
  state,
  dispatch,
  loading,
  onSearch,
  snap,
  onAdvanceSnap,
}: Props) {
  const { phase, route, selected, errorMessage } = state;
  const headline = peekHeadline(state, loading);
  const panelRef = useRef<HTMLElement>(null);
  const skipMotion = useRef(true);

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    const desktop = window.matchMedia("(min-width: 900px)").matches;
    if (desktop) {
      el.style.height = "";
      return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nextVar = sheetHeightVar(snap);
    if (skipMotion.current || reduce) {
      skipMotion.current = false;
      el.style.height = nextVar;
      return;
    }
    const from = el.getBoundingClientRect().height;
    el.style.height = nextVar;
    const to = el.getBoundingClientRect().height;
    el.style.height = `${from}px`;
    animate(el, {
      height: [`${from}px`, `${to}px`],
      duration: 220,
      ease: "outQuad",
    });
  }, [snap]);

  return (
    <section ref={panelRef} className={`panel snap-${snap}`}>
      <button
        type="button"
        className="sheet-handle"
        aria-label="シート"
        aria-expanded={snap !== "peek"}
        onClick={onAdvanceSnap}
      />
      {snap === "peek" && (
      <div className="sheet-peek">
        {showPeekSearch(phase, loading, snap) ? (
          <button
            type="button"
            className="primary-btn"
            disabled={loading}
            onClick={onSearch}
          >
            {copy.search}
          </button>
        ) : phase === "S5" ? (
          <div className="row">
            <p>{errorMessage}</p>
            <button
              type="button"
              onClick={() => dispatch({ type: "CLEAR_ERROR" })}
            >
              {copy.close}
            </button>
          </div>
        ) : (
          <p className="peek-line">{headline}</p>
        )}
      </div>
      )}

      <div className="sheet-body">
        <label className="sheet-water">
          <input
            type="checkbox"
            checked={state.waterVisible}
            onChange={() => dispatch({ type: "TOGGLE_WATER" })}
          />
          {copy.waterToggle}
        </label>

        {phase === "S0" && <p className="muted">{copy.s0sub}</p>}

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
              <button
                type="button"
                className="primary-btn"
                disabled={loading}
                onClick={onSearch}
              >
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
              <>
                <p>{copy.sameRoute}</p>
                <p className="muted">{formatContinuousSun(route.shortest)}</p>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className={
                    selected === "shortest" ? "path-card active" : "path-card"
                  }
                  onClick={() => dispatch({ type: "SELECT", which: "shortest" })}
                >
                  <ShadeRing pct={route.shortest.shade_pct} tone="short" />
                  <span className="path-card-text">
                    <strong>{copy.legendShortest}</strong>{" "}
                    {formatPath(route.shortest)}
                    <span className="muted">
                      {formatContinuousSun(route.shortest)}
                    </span>
                  </span>
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
                    <ShadeRing pct={route.shadiest.shade_pct} tone="shade" />
                    <span className="path-card-text">
                      <strong>{copy.legendShade}</strong>{" "}
                      {formatPath(route.shadiest)}
                      <span className="muted">
                        {formatContinuousSun(route.shadiest)}
                      </span>
                    </span>
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
              <strong>{copy.legendShortest}</strong> {route.shortest.distance_m}
              m · {route.shortest.duration_min}分
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
      </div>
    </section>
  );
}
