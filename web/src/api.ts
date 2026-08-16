import type { PathDto, Pin, RouteResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchBoundary(): Promise<GeoJSON.GeoJSON> {
  const res = await fetch(`${BASE}/boundary`);
  return res.json();
}

export async function fetchShadows(
  iso: string,
): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(
    `${BASE}/shadows?datetime=${encodeURIComponent(iso)}`,
  );
  return res.json();
}

export async function postRoutes(
  origin: Pin,
  destination: Pin,
  iso: string,
): Promise<RouteResponse> {
  const res = await fetch(`${BASE}/routes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: { lon: origin.lon, lat: origin.lat },
      destination: { lon: destination.lon, lat: destination.lat },
      datetime: iso,
    }),
  });
  const body = await res.json();
  if (!res.ok) {
    const message =
      body?.detail?.message ??
      body?.message ??
      "しばらくしてからもう一度お試しください";
    throw new Error(message);
  }
  return body as RouteResponse;
}

export function localInputToIso(local: string): string {
  return `${local}:00+09:00`;
}

export function formatPath(p: PathDto): string {
  return `${p.distance_m}m · ${p.duration_min}分 · 日陰 ${p.shade_pct}%`;
}
