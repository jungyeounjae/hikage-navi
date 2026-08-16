import { useCallback, useEffect, useReducer, useState } from "react";
import {
  fetchBoundary,
  fetchShadows,
  localInputToIso,
  postRoutes,
} from "./api";
import { copy } from "./copy";
import { MapView } from "./MapView";
import { Panel } from "./Panel";
import { TopBar } from "./TopBar";
import { initialState, reduce } from "./state";
import type { Pin } from "./types";
import "./styles.css";

export function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  const [boundary, setBoundary] = useState<GeoJSON.GeoJSON | null>(null);
  const [shadows, setShadows] = useState<GeoJSON.FeatureCollection | null>(
    null,
  );
  const [mapReady, setMapReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [night, setNight] = useState(false);

  const onMapReady = useCallback(() => setMapReady(true), []);
  const onTap = useCallback((point: Pin) => {
    dispatch({ type: "MAP_TAP", point });
  }, []);

  useEffect(() => {
    fetchBoundary()
      .then(setBoundary)
      .catch(() => {
        /* map still usable; boundary optional until API up */
      });
  }, []);

  useEffect(() => {
    const iso = localInputToIso(state.datetimeLocal);
    let cancelled = false;
    fetchShadows(iso)
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
  }, [state.datetimeLocal]);

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
    <div className="app">
      <TopBar state={state} dispatch={dispatch} night={night} />
      <MapView
        state={state}
        boundary={boundary}
        shadows={shadows}
        mapReady={mapReady}
        onMapReady={onMapReady}
        onTap={onTap}
      />
      <Panel
        state={state}
        dispatch={dispatch}
        loading={loading}
        onSearch={onSearch}
        boundary={boundary}
      />
    </div>
  );
}
