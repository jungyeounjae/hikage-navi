import { useEffect, useRef, type MutableRefObject } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { copy } from "./copy";
import type { AppState, Bbox, Pin } from "./types";
import { pointInBoundary } from "./geo";
import { waterPopupHtml } from "./api";

type Props = {
  state: AppState;
  boundary: GeoJSON.GeoJSON | null;
  shadows: GeoJSON.FeatureCollection | null;
  mapReady: boolean;
  onMapReady: () => void;
  onTap: (point: Pin) => void;
  onViewportChange: (bbox: Bbox) => void;
  onToggleWater: () => void;
};

const EMPTY: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

function lineFeature(
  coords: [number, number][],
): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: coords },
      },
    ],
  };
}

export function MapView({
  state,
  boundary,
  shadows,
  mapReady,
  onMapReady,
  onTap,
  onViewportChange,
  onToggleWater,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const originMarker = useRef<maplibregl.Marker | null>(null);
  const destMarker = useRef<maplibregl.Marker | null>(null);
  const waterMarkers = useRef<maplibregl.Marker[]>([]);
  const boundaryRef = useRef(boundary);
  boundaryRef.current = boundary;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: [
              "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
            ],
            tileSize: 256,
            attribution: "国土地理院",
          },
        },
        layers: [{ id: "gsi", type: "raster", source: "gsi" }],
      },
      center: [139.7016, 35.658],
      zoom: 15,
      pitch: 0,
      bearing: 0,
      interactive: true,
    });

    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();

    map.on("load", () => {
      map.addSource("boundary", {
        type: "geojson",
        data: EMPTY,
      });
      map.addLayer({
        id: "boundary-line",
        type: "line",
        source: "boundary",
        paint: { "line-color": "#334155", "line-width": 2 },
      });

      map.addSource("shadows", {
        type: "geojson",
        data: EMPTY,
      });
      map.addLayer({
        id: "shadows-fill",
        type: "fill",
        source: "shadows",
        paint: { "fill-color": "#0f172a", "fill-opacity": 0.35 },
      });

      map.addSource("shortest", {
        type: "geojson",
        data: EMPTY,
      });
      map.addLayer({
        id: "shortest-line",
        type: "line",
        source: "shortest",
        paint: { "line-color": "#1d4ed8", "line-width": 4 },
      });

      map.addSource("shadiest", {
        type: "geojson",
        data: EMPTY,
      });
      map.addLayer({
        id: "shadiest-line",
        type: "line",
        source: "shadiest",
        paint: { "line-color": "#b45309", "line-width": 5 },
      });

      onMapReady();
      reportViewport();
    });

    function reportViewport() {
      const b = map.getBounds();
      onViewportChange([
        b.getWest(),
        b.getSouth(),
        b.getEast(),
        b.getNorth(),
      ]);
    }

    map.on("moveend", reportViewport);

    map.on("click", (e) => {
      const lon = e.lngLat.lng;
      const lat = e.lngLat.lat;
      const inBoundary = pointInBoundary(lon, lat, boundaryRef.current);
      onTap({ lon, lat, inBoundary });
    });

    mapRef.current = map;
    return () => {
      originMarker.current?.remove();
      destMarker.current?.remove();
      for (const marker of waterMarkers.current) marker.remove();
      waterMarkers.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, [onMapReady, onTap, onViewportChange]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !boundary) return;
    const src = map.getSource("boundary") as maplibregl.GeoJSONSource | undefined;
    src?.setData(boundary as GeoJSON.Feature | GeoJSON.FeatureCollection);
  }, [boundary, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("shadows") as maplibregl.GeoJSONSource | undefined;
    src?.setData(shadows ?? EMPTY);
  }, [shadows, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const shortestSrc = map.getSource(
      "shortest",
    ) as maplibregl.GeoJSONSource | undefined;
    const shadiestSrc = map.getSource(
      "shadiest",
    ) as maplibregl.GeoJSONSource | undefined;
    const route = state.route;
    if (!route) {
      shortestSrc?.setData(EMPTY);
      shadiestSrc?.setData(EMPTY);
      return;
    }
    if (route.same_route || !route.shadiest) {
      shortestSrc?.setData(lineFeature(route.shortest.coordinates));
      shadiestSrc?.setData(EMPTY);
    } else {
      shortestSrc?.setData(lineFeature(route.shortest.coordinates));
      shadiestSrc?.setData(lineFeature(route.shadiest.coordinates));
    }
  }, [state.route, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    function setMarker(
      ref: MutableRefObject<maplibregl.Marker | null>,
      pin: Pin | null,
      label: string,
    ) {
      if (!pin) {
        ref.current?.remove();
        ref.current = null;
        return;
      }
      if (!ref.current) {
        // MapLibre가 루트 요소에 위치용 클래스를 붙인다. 라벨은 안쪽에 둔다
        const root = document.createElement("div");
        const labelEl = document.createElement("div");
        labelEl.className = "pin";
        labelEl.textContent = label;
        root.appendChild(labelEl);
        ref.current = new maplibregl.Marker({ element: root })
          .setLngLat([pin.lon, pin.lat])
          .addTo(map!);
      } else {
        ref.current.setLngLat([pin.lon, pin.lat]);
      }
      const labelEl = ref.current.getElement().querySelector(".pin");
      labelEl?.classList.toggle("pin-out", !pin.inBoundary);
    }

    setMarker(originMarker, state.origin, "出発");
    setMarker(destMarker, state.destination, "到着");
  }, [state.origin, state.destination]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const marker of waterMarkers.current) marker.remove();
    waterMarkers.current = [];

    const path =
      state.selected === "shadiest" && state.route?.shadiest
        ? state.route.shadiest
        : state.route?.shortest;
    const spots = state.waterVisible && path ? path.water_spots : [];

    for (const spot of spots) {
      const root = document.createElement("div");
      const labelEl = document.createElement("div");
      labelEl.className = "water-pin";
      labelEl.textContent = "💧";
      root.appendChild(labelEl);
      const marker = new maplibregl.Marker({ element: root })
        .setLngLat([spot.lon, spot.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(waterPopupHtml(spot)),
        )
        .addTo(map);
      waterMarkers.current.push(marker);
    }
  }, [state.route, state.selected, state.waterVisible, mapReady]);

  return (
    <div className="map-wrap">
      {!mapReady && <div className="map-loading">{copy.loadingMap}</div>}
      <div ref={containerRef} className="map" />
      <div className="legend">
        <span>
          <i className="swatch short" />
          {copy.legendShortest}
        </span>
        <span>
          <i className="swatch shade" />
          {copy.legendShade}
        </span>
        <label className="legend-water">
          <input
            type="checkbox"
            checked={state.waterVisible}
            onChange={onToggleWater}
          />
          💧 {copy.waterToggle}
        </label>
      </div>
    </div>
  );
}
