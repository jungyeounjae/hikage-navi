import { copy } from "./copy";
import type { Bbox, PathDto, Pin, RouteResponse, WaterSpotDto } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchBoundary(): Promise<GeoJSON.GeoJSON> {
  const res = await fetch(`${BASE}/boundary`);
  return res.json();
}

export function shadowsQuery(iso: string, bbox?: Bbox): string {
  const params = new URLSearchParams({ datetime: iso });
  if (bbox) params.set("bbox", bbox.map((v) => v.toFixed(4)).join(","));
  return params.toString();
}

export async function fetchShadows(
  iso: string,
  bbox?: Bbox,
): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${BASE}/shadows?${shadowsQuery(iso, bbox)}`);
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

export function formatContinuousSun(p: PathDto): string {
  const s = p.max_continuous_sun_seconds;
  const min = Math.floor(s / 60);
  const sec = s % 60;
  const label =
    min === 0 ? `${sec}秒` : sec === 0 ? `${min}分` : `${min}分${sec}秒`;
  return copy.continuousSun(label);
}

const OSM_ACCESS_MACHINE_TAGS = new Set([
  "yes",
  "no",
  "private",
  "permissive",
  "customers",
  "unknown",
]);

function isOsmAccessMachineTag(value: string): boolean {
  return OSM_ACCESS_MACHINE_TAGS.has(value.trim().toLowerCase());
}

export function waterPopupLines(spot: WaterSpotDto): string[] {
  const lines: string[] = [];
  if (spot.name) lines.push(spot.name);
  else lines.push("給水スポット");
  lines.push("💧 給水可能");
  lines.push(`ルートから約${spot.route_distance_m}m`);
  if (spot.bottle_refill) lines.push("マイボトル給水可能");
  if (spot.access && !isOsmAccessMachineTag(spot.access)) {
    lines.push(spot.access);
  }
  if (spot.opening_hours) lines.push(`利用時間 ${spot.opening_hours}`);
  return lines;
}

export function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function waterPopupHtml(spot: WaterSpotDto): string {
  return waterPopupLines(spot).map(escapeHtml).join("<br>");
}
