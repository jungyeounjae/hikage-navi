from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from shapely.geometry import LineString, Point

from hikage_navi.constants import WATER_BUFFER_M
from hikage_navi.geo import to_planar


@dataclass
class WaterSpot:
    id: str
    name: str | None
    lat: float
    lon: float
    type: str
    source: str
    bottle_refill: bool | None
    access: str | None
    opening_hours: str | None


@dataclass
class WaterSpotMatch(WaterSpot):
    route_distance_m: int


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_water_spots(path: Path) -> list[WaterSpot]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    spots: list[WaterSpot] = []
    for feat in raw.get("features", []):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = float(geom["coordinates"][0]), float(geom["coordinates"][1])
        props = feat.get("properties") or {}
        spot_id = props.get("id") or f"{lon:.5f},{lat:.5f}"
        bottle_refill = True if props.get("bottle") == "yes" else None
        spots.append(
            WaterSpot(
                id=str(spot_id),
                name=_blank_to_none(props.get("name")),
                lat=lat,
                lon=lon,
                type=str(props.get("type") or "DRINKING_WATER"),
                source=str(props.get("source") or "OSM"),
                bottle_refill=bottle_refill,
                access=_blank_to_none(props.get("access")),
                opening_hours=_blank_to_none(props.get("opening_hours")),
            )
        )
    return spots


def nearby_water_spots(
    spots: list[WaterSpot],
    route_coords: list[tuple[float, float]],
    buffer_m: float = WATER_BUFFER_M,
) -> list[WaterSpotMatch]:
    if not spots:
        return []
    route_xy = [to_planar(lon, lat) for lon, lat in route_coords]
    line = LineString(route_xy)
    matches: list[WaterSpotMatch] = []
    for spot in spots:
        distance = line.distance(Point(*to_planar(spot.lon, spot.lat)))
        if distance <= buffer_m:
            matches.append(
                WaterSpotMatch(
                    **asdict(spot),
                    route_distance_m=int(round(distance)),
                )
            )
    matches.sort(key=lambda m: m.route_distance_m)
    return matches
