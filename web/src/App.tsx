import { useCallback, useEffect, useReducer, useState } from "react";
import {
  fetchBoundary,
  fetchShadows,
  localInputToIso,
  postRoutes,
} from "./api";
import { copy } from "./copy";
import { MapView } from "./MapView";
import { LocationFab, Panel, createLocateHandler } from "./Panel";
import { TopBar } from "./TopBar";
import { initialState, reduce } from "./state";
import {
  advanceSheetSnap,
  sheetAfterMapTap,
  type SheetSnap,
} from "./sheet";
import type { Bbox, Pin } from "./types";
import "./styles.css";

/** 지도를 아주 조금 움직였다고 그림자를 다시 받지는 않는다 */
function sameViewport(a: Bbox, b: Bbox): boolean {
  return a.every((v, i) => Math.abs(v - b[i]) < 0.0005);
}

export function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  const [boundary, setBoundary] = useState<GeoJSON.GeoJSON | null>(null);
  const [shadows, setShadows] = useState<GeoJSON.FeatureCollection | null>(
    null,
  );
  const [mapReady, setMapReady] = useState(false);
  const [viewport, setViewport] = useState<Bbox | null>(null);
  const [loading, setLoading] = useState(false);
  const [night, setNight] = useState(false);
  const [sheetSnap, setSheetSnap] = useState<SheetSnap>("peek");

  const onMapReady = useCallback(() => setMapReady(true), []);
  const onViewportChange = useCallback((bbox: Bbox) => {
    setViewport((prev) => (prev && sameViewport(prev, bbox) ? prev : bbox));
  }, []);
  const onTap = useCallback((point: Pin) => {
    dispatch({ type: "MAP_TAP", point });
    setSheetSnap(sheetAfterMapTap());
  }, []);
  const locate = useCallback(
    () => createLocateHandler(dispatch, boundary)(),
    [boundary],
  );

  useEffect(() => {
    fetchBoundary()
      .then(setBoundary)
      .catch(() => {
        /* map still usable; boundary optional until API up */
      });
  }, []);

  useEffect(() => {
    if (!viewport) return;
    const iso = localInputToIso(state.datetimeLocal);
    let cancelled = false;
    fetchShadows(iso, viewport)
      .then((fc) => {
        if (cancelled) return;
        setNight(Boolean((fc as { night?: boolean }).night));
        if ((fc as { night?: boolean }).night) {
          setShadows({ type: "FeatureCollection", features: [] });
        } else {
          setShadows(fc);
        }
      })
      .catch(() => {
        if (!cancelled) setShadows({ type: "FeatureCollection", features: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [state.datetimeLocal, viewport]);

  async function runSearch(origin: Pin, destination: Pin, datetimeLocal: string) {
    setLoading(true);
    try {
      const route = await postRoutes(
        origin,
        destination,
        localInputToIso(datetimeLocal),
      );
      dispatch({ type: "ROUTE_OK", route });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : copy.errors.server;
      dispatch({ type: "ROUTE_ERR", message });
    } finally {
      setLoading(false);
    }
  }

  function onSearch() {
    if (!state.origin || !state.destination) return;
    void runSearch(state.origin, state.destination, state.datetimeLocal);
  }

  useEffect(() => {
    if (state.phase !== "S3" && state.phase !== "S4") return;
    if (!state.origin || !state.destination) return;
    void runSearch(state.origin, state.destination, state.datetimeLocal);
    // datetime change while comparing → re-search; origin/dest stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.datetimeLocal]);

  return (
    <div className={`app snap-${sheetSnap}`}>
      <MapView
        state={state}
        boundary={boundary}
        shadows={shadows}
        mapReady={mapReady}
        onMapReady={onMapReady}
        onTap={onTap}
        onViewportChange={onViewportChange}
        onToggleWater={() => dispatch({ type: "TOGGLE_WATER" })}
      />
      <TopBar state={state} dispatch={dispatch} night={night} />
      <LocationFab onClick={locate} />
      <Panel
        state={state}
        dispatch={dispatch}
        loading={loading}
        onSearch={onSearch}
        snap={sheetSnap}
        onAdvanceSnap={() => setSheetSnap((s) => advanceSheetSnap(s))}
      />
    </div>
  );
}
