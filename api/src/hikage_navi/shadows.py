from __future__ import annotations

from collections.abc import Sequence
from math import cos, radians, sin, tan

import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from hikage_navi.constants import MIN_SUN_ALTITUDE_DEG
from hikage_navi.exposure import max_run_sun_m
from hikage_navi.geo import expand_bbox, from_planar, to_planar, to_planar_array
from hikage_navi.sun import shadow_length_m

MIN_BUILDING_HEIGHT_M = 2.0
MAX_SHADOW_MARGIN_M = 500.0
SAMPLE_STEP_M = 5.0
RENDER_SIMPLIFY_M = 1.0
MAX_SAMPLES = 200


def _to_xy(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda lon, lat: to_planar(lon, lat), geom)


def _to_lonlat(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda x, y: from_planar(x, y), geom)


def _shadow_direction(azimuth_deg: float) -> tuple[float, float]:
    """태양 반대 방향 단위 벡터. 북=0 시계방향 → 수학각: 90-az"""
    math_rad = radians(90.0 - azimuth_deg)
    return -cos(math_rad), -sin(math_rad)


def building_shadow(
    footprint_lonlat: Polygon,
    height_m: float,
    altitude_deg: float,
    azimuth_deg: float,
) -> Polygon:
    length = shadow_length_m(height_m, altitude_deg)
    ux, uy = _shadow_direction(azimuth_deg)
    dx, dy = length * ux, length * uy
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
        if h >= MIN_BUILDING_HEIGHT_M
    ]
    if not polys:
        return Polygon()
    return unary_union(polys)


def shadow_margin_m(altitude_deg: float, max_height_m: float) -> float:
    """이 고도에서 가장 높은 건물이 드리울 수 있는 그림자 길이(상한 적용)."""
    return min(MAX_SHADOW_MARGIN_M, shadow_length_m(max_height_m, altitude_deg))


class BuildingIndex:
    """건물 풋프린트 STRtree. 요청 범위 주변 건물만 골라 그림자 계산량을 줄인다."""

    def __init__(self, buildings: Sequence[tuple[BaseGeometry, float]]):
        self._items = [
            (geom, float(height))
            for geom, height in buildings
            if geom is not None and not geom.is_empty
        ]

        self._tree = STRtree([g for g, _ in self._items]) if self._items else None
        self.max_height_m = max((h for _, h in self._items), default=0.0)

    def select(
        self, bbox: tuple[float, float, float, float], margin_m: float = 0.0
    ) -> list[tuple[BaseGeometry, float]]:
        if self._tree is None:
            return []
        window = box(*expand_bbox(bbox, margin_m))
        return [self._items[i] for i in self._tree.query(window, predicate="intersects")]


def _flatten_polygons(geom: BaseGeometry) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    parts: list[Polygon] = []
    for part in getattr(geom, "geoms", []):
        parts.extend(_flatten_polygons(part))
    return parts


class ShadowIndex:
    """평면좌표(EPSG:6677) 그림자 폴리곤 + STRtree.

    도시 전체 그림자를 하나로 union하면 간선마다 거대 지오메트리를 다뤄야 해
    실데이터(4만 동)에서 응답이 분 단위로 늘어난다. 폴리곤을 개별로 두고
    공간 색인으로 후보만 좁힌다.
    """

    def __init__(self, polygons_xy):
        arr = np.asarray(polygons_xy, dtype=object)
        self._polys = list(arr[~shapely.is_empty(arr)]) if arr.size else []
        if self._polys:
            shapely.prepare(self._polys)
        self._tree = STRtree(self._polys) if self._polys else None

    @property
    def is_empty(self) -> bool:
        return not self._polys

    @classmethod
    def from_buildings(
        cls,
        buildings: Sequence[tuple[BaseGeometry, float]],
        altitude_deg: float,
        azimuth_deg: float,
    ) -> ShadowIndex:
        tall = [
            (geom, float(height))
            for geom, height in buildings
            if geom is not None and float(height) >= MIN_BUILDING_HEIGHT_M
        ]
        if not tall:
            return cls([])
        geoms = np.array([g for g, _ in tall], dtype=object)
        tall_heights = np.array([h for _, h in tall], dtype=float)
        geoms = geoms[~shapely.is_empty(geoms)]
        # MultiPolygon 건물은 개별 폴리곤으로 펼친다
        arr, part_of = shapely.get_parts(geoms, return_index=True)
        heights = tall_heights[part_of]
        if arr.size == 0:
            return cls([])
        foot_xy = shapely.set_coordinates(
            shapely.transform(arr, lambda c: c.copy()),
            to_planar_array(shapely.get_coordinates(arr)),
        )

        alt = max(altitude_deg, MIN_SUN_ALTITUDE_DEG)
        lengths = heights / tan(radians(alt))
        ux, uy = _shadow_direction(azimuth_deg)
        offsets = np.column_stack([lengths * ux, lengths * uy])
        counts = shapely.get_num_coordinates(foot_xy)
        roof_coords = shapely.get_coordinates(foot_xy) + np.repeat(
            offsets, counts, axis=0
        )
        roof_xy = shapely.set_coordinates(
            shapely.transform(foot_xy, lambda c: c.copy()), roof_coords
        )
        pairs = shapely.geometrycollections(np.column_stack([foot_xy, roof_xy]))
        hulls = shapely.convex_hull(pairs)
        return cls(list(hulls))

    @classmethod
    def from_geometry(cls, geom: BaseGeometry | None) -> ShadowIndex:
        if geom is None:
            return cls([])
        return cls(_flatten_polygons(_to_xy(geom)))

    def shade_length_m(self, coords_lonlat: Sequence[tuple[float, float]]) -> float:
        return float(self.shade_lengths([coords_lonlat])[0])

    def sample_shade(
        self, coords: Sequence[tuple[float, float]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """한 선의 샘플 구간 길이와 그늘 여부. 트리가 비면 전부 SUN(False)."""
        usable, owner, step, shaded = self._sample_shade_batch([coords])
        if not usable:
            return np.array([], dtype=float), np.array([], dtype=bool)
        return step, shaded

    def max_continuous_sun_m(self, coords: Sequence[tuple[float, float]]) -> float:
        steps, shaded = self.sample_shade(coords)
        return max_run_sun_m(shaded, steps)

    def _sample_shade_batch(
        self, coords_list: Sequence[Sequence[tuple[float, float]]]
    ) -> tuple[list[int], np.ndarray, np.ndarray, np.ndarray]:
        usable = [i for i, c in enumerate(coords_list) if len(c) >= 2]
        if not usable:
            empty = np.array([], dtype=float)
            return usable, empty.astype(int), empty, np.array([], dtype=bool)

        counts = np.array([len(coords_list[i]) for i in usable])
        xy = to_planar_array(
            np.concatenate([np.asarray(coords_list[i], dtype=float) for i in usable])
        )
        lines = shapely.linestrings(
            xy, indices=np.repeat(np.arange(len(usable)), counts)
        )
        lengths = shapely.length(lines)
        samples = np.clip(np.ceil(lengths / SAMPLE_STEP_M), 1, MAX_SAMPLES).astype(int)
        owner = np.repeat(np.arange(len(usable)), samples)
        step = (lengths / samples)[owner]
        # 각 구간의 중점을 대표점으로 삼는다
        rank = np.arange(len(owner)) - np.repeat(np.cumsum(samples) - samples, samples)
        points = shapely.line_interpolate_point(lines[owner], (rank + 0.5) * step)

        shaded = np.zeros(len(points), dtype=bool)
        if self._tree is not None:
            hit, _ = self._tree.query(points, predicate="intersects")
            if hit.size:
                shaded[hit] = True
        return usable, owner, step, shaded

    def shade_lengths(self, coords_list: Sequence[Sequence[tuple[float, float]]]):
        """여러 선의 그늘 길이를 한 번에 구한다.

        선×그림자 교차를 정확히 계산하면 저녁처럼 그림자가 긴 시간대에
        교차쌍이 수십만 개로 불어나 응답이 10초를 넘는다. SAMPLE_STEP_M 간격
        샘플점의 포함 여부로 근사한다 (간선당 오차 ≤ 샘플 간격).
        """
        out = np.zeros(len(coords_list))
        if self._tree is None:
            return out
        usable, owner, step, shaded = self._sample_shade_batch(coords_list)
        if not usable:
            return out
        out[usable] = np.bincount(
            owner[shaded], weights=step[shaded], minlength=len(usable)
        )
        return out

    def union_lonlat(
        self, bbox: tuple[float, float, float, float] | None = None
    ) -> BaseGeometry:
        if self._tree is None:
            return Polygon()
        if bbox is None:
            polys = self._polys
        else:
            # 화면 밖을 먼저 잘라야 union이 빠르다
            window = _to_xy(box(*bbox))
            hits = self._tree.query(window, predicate="intersects")
            if hits.size == 0:
                return Polygon()
            clipped = shapely.intersection(
                np.array(self._polys, dtype=object)[hits], window
            )
            polys = list(clipped[~shapely.is_empty(clipped)])
        if not polys:
            return Polygon()
        # 표시용이라 1 m 이하 굴곡은 버린다 (응답 크기 ~35% 감소)
        return _to_lonlat(shapely.simplify(shapely.union_all(polys), RENDER_SIMPLIFY_M))
