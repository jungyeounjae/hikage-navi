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


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and value != value


def spot_from_properties(props: dict, lon: float, lat: float) -> WaterSpot:
    """Map OSM or processed GeoJSON properties to WaterSpot. Does not invent names."""
    amenity = props.get("amenity")
    drinking_water = props.get("drinking_water")
    if amenity == "drinking_water" or drinking_water == "yes":
        spot_type = "DRINKING_WATER"
        source = "OSM"
    else:
        spot_type = str(props.get("type") or "DRINKING_WATER")
        source = str(props.get("source") or "OSM")
    name_raw = props.get("name")
    if name_raw is None or _is_nan(name_raw):
        name = None
    else:
        name = _blank_to_none(name_raw)
    spot_id = props.get("id")
    if spot_id is None or _is_nan(spot_id) or str(spot_id).strip() == "":
        spot_id = f"{lon:.5f},{lat:.5f}"
    bottle_refill = True if props.get("bottle") == "yes" else None
    return WaterSpot(
        id=str(spot_id),
        name=name,
        lat=lat,
        lon=lon,
        type=spot_type,
        source=source,
        bottle_refill=bottle_refill,
        access=_blank_to_none(props.get("access")) if not _is_nan(props.get("access")) else None,
        opening_hours=(
            _blank_to_none(props.get("opening_hours"))
            if not _is_nan(props.get("opening_hours"))
            else None
        ),
    )


def water_spot_feature_properties(spot: WaterSpot, bottle: object = None) -> dict:
    if bottle is None and spot.bottle_refill is True:
        bottle = "yes"
    return {
        "id": spot.id,
        "name": spot.name,
        "type": spot.type,
        "source": spot.source,
        "bottle": bottle if bottle == "yes" else None,
        "access": spot.access,
        "opening_hours": spot.opening_hours,
    }


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
        spots.append(spot_from_properties(props, lon=lon, lat=lat))
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
