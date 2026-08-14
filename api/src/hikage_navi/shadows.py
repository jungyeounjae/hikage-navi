from math import cos, radians, sin

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from hikage_navi.geo import from_planar, to_planar
from hikage_navi.sun import shadow_length_m


def _to_xy(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda lon, lat: to_planar(lon, lat), geom)


def _to_lonlat(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda x, y: from_planar(x, y), geom)


def building_shadow(
    footprint_lonlat: Polygon,
    height_m: float,
    altitude_deg: float,
    azimuth_deg: float,
) -> Polygon:
    length = shadow_length_m(height_m, altitude_deg)
    # 태양 반대 방향. 북=0 시계방향 → 수학각: 90-az
    math_rad = radians(90.0 - azimuth_deg)
    dx = -length * cos(math_rad)
    dy = -length * sin(math_rad)
    foot_xy = _to_xy(footprint_lonlat)
    roof_xy = transform(lambda x, y: (x + dx, y + dy), foot_xy)
    pts = list(foot_xy.exterior.coords) + list(roof_xy.exterior.coords)
    hull = Polygon(pts).convex_hull
    return _to_lonlat(hull)


def all_shadows(
    buildings: list[tuple[Polygon, float]],
    altitude_deg: float,
    azimuth_deg: float,
) -> BaseGeometry:
    polys = [
        building_shadow(poly, h, altitude_deg, azimuth_deg)
        for poly, h in buildings
        if h >= 2.0
    ]
    if not polys:
        return Polygon()
    return unary_union(polys)
