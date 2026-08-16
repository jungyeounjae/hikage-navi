from math import asin, cos, radians, sin, sqrt

import numpy as np
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


def to_planar_array(coords):
    """(N, 2) 경위도 배열 → 평면좌표 배열. 좌표별 호출 오버헤드를 없앤다."""
    x, y = _TO_PLANAR.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([x, y])


def from_planar_array(coords):
    lon, lat = _FROM_PLANAR.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([lon, lat])


def bbox_of(points) -> tuple[float, float, float, float]:
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)


def expand_bbox(bbox, margin_m: float) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    dlat = margin_m / 111_320.0
    mid_lat = radians((min_lat + max_lat) / 2)
    dlon = margin_m / max(1.0, 111_320.0 * cos(mid_lat))
    return min_lon - dlon, min_lat - dlat, max_lon + dlon, max_lat + dlat


def point_in_boundary(lon: float, lat: float, boundary: BaseGeometry) -> bool:
    pt = Point(lon, lat)
    return bool(boundary.covers(pt))
