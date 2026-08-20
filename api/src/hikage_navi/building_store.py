from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shapely.geometry import shape

from hikage_navi.geo import expand_bbox
from hikage_navi.shadows import BuildingIndex, MAX_SHADOW_MARGIN_M


def _bounds_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


@dataclass(frozen=True)
class _WardEntry:
    code: str
    bounds: tuple[float, float, float, float]
    buildings_path: Path
    max_height_m: float


class BuildingStore:
    """구별 buildings.geojson을 bbox와 교차하는 구만 읽어 BuildingIndex로 합친다."""

    def __init__(self, wards_dir: Path):
        self._wards_dir = wards_dir
        self._wards: list[_WardEntry] = []
        for child in sorted(wards_dir.iterdir()):
            if not child.is_dir():
                continue
            buildings_path = child / "buildings.geojson"
            if not buildings_path.is_file():
                continue
            meta_path = child / "meta.json"
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                bounds = tuple(meta["bounds"])
                max_h = float(meta.get("max_height_m", 0.0))
            else:
                bounds, max_h = _bounds_from_geojson(buildings_path)
            self._wards.append(
                _WardEntry(child.name, bounds, buildings_path, max_h)
            )
        self.max_height_m = max((w.max_height_m for w in self._wards), default=0.0)

    def _codes_for_bbox(
        self, bbox: tuple[float, float, float, float], margin_m: float
    ) -> list[str]:
        window = expand_bbox(bbox, margin_m)
        return [w.code for w in self._wards if _bounds_intersect(w.bounds, window)]

    @lru_cache(maxsize=32)
    def _load_ward(self, code: str) -> tuple[tuple, ...]:
        path = self._wards_dir / code / "buildings.geojson"
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = []
        for f in raw.get("features", []):
            items.append((shape(f["geometry"]), float(f["properties"]["height"])))
        return tuple(items)

    def buildings_in_bbox(
        self, bbox: tuple[float, float, float, float], margin_m: float = 0.0
    ) -> BuildingIndex:
        codes = self._codes_for_bbox(bbox, margin_m)
        items: list[tuple] = []
        for code in codes:
            items.extend(self._load_ward(code))
        return BuildingIndex(items)

    def select_for_shadow(
        self,
        bbox: tuple[float, float, float, float],
        margin_m: float,
    ) -> list[tuple]:
        """bbox 주변 구만 로드한 뒤 건물 STRtree로 margin만큼 더 좁힌다."""
        pre = self.buildings_in_bbox(bbox, margin_m=MAX_SHADOW_MARGIN_M)
        return pre.select(bbox, margin_m=margin_m)


def _bounds_from_geojson(path: Path) -> tuple[tuple[float, float, float, float], float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    max_h = 0.0
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for f in raw.get("features", []):
        geom = shape(f["geometry"])
        bx = geom.bounds
        minx, miny = min(minx, bx[0]), min(miny, bx[1])
        maxx, maxy = max(maxx, bx[2]), max(maxy, bx[3])
        max_h = max(max_h, float(f["properties"].get("height", 0.0)))
    if minx == float("inf"):
        return (0.0, 0.0, 0.0, 0.0), 0.0
    return (minx, miny, maxx, maxy), max_h
