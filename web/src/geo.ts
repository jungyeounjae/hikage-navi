export function pointInBoundary(
  lon: number,
  lat: number,
  geojson: GeoJSON.GeoJSON | null,
): boolean {
  if (!geojson) return true;
  const geom =
    geojson.type === "Feature"
      ? geojson.geometry
      : geojson.type === "FeatureCollection"
        ? geojson.features[0]?.geometry
        : geojson;
  if (!geom) return true;
  if (geom.type === "Polygon") {
    return ringContains(lon, lat, geom.coordinates[0]);
  }
  if (geom.type === "MultiPolygon") {
    return geom.coordinates.some((poly) => ringContains(lon, lat, poly[0]));
  }
  return true;
}

function ringContains(
  lon: number,
  lat: number,
  ring: number[][],
): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect =
      yi > lat !== yj > lat &&
      lon < ((xj - xi) * (lat - yi)) / (yj - yi + Number.EPSILON) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}
