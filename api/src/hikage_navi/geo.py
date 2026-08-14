from math import asin, cos, radians, sin, sqrt

from pyproj import Transformer
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import GEOGRAPHIC_CRS, PLANAR_CRS

_TO_PLANAR = Transformer.from_crs(GEOGRAPHIC_CRS, PLANAR_CRS, always_xy=True)
_FROM_PLANAR = Transformer.from_crs(PLANAR_CRS, GEOGRAPHIC_CRS, always_xy=True)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def to_planar(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TO_PLANAR.transform(lon, lat)
    return float(x), float(y)


def from_planar(x: float, y: float) -> tuple[float, float]:
    lon, lat = _FROM_PLANAR.transform(x, y)
    return float(lon), float(lat)


def point_in_boundary(lon: float, lat: float, boundary: BaseGeometry) -> bool:
    pt = Point(lon, lat)
    return bool(boundary.covers(pt))
