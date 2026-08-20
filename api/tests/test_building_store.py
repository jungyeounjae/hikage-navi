"""BuildingStore: tokyo23 구별 GeoJSON을 bbox로 고른다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box, shape

from hikage_navi.building_store import BuildingStore
from hikage_navi.geo import expand_bbox


def _write_ward(
    root: Path,
    code: str,
    lon: float,
    lat: float,
    *,
    height: float = 10.0,
) -> None:
    ward_dir = root / code
    ward_dir.mkdir(parents=True, exist_ok=True)
    footprint = box(lon, lat, lon + 0.001, lat + 0.001)
    feature = {
        "type": "Feature",
        "properties": {"height": height},
        "geometry": json.loads(json.dumps(footprint.__geo_interface__)),
    }
    bounds = footprint.bounds
    (ward_dir / "buildings.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]}),
        encoding="utf-8",
    )
    (ward_dir / "meta.json").write_text(
        json.dumps({"bounds": list(bounds), "max_height_m": height}),
        encoding="utf-8",
    )


@pytest.fixture
def ward_root(tmp_path: Path) -> Path:
    wards = tmp_path / "wards"
    wards.mkdir()
    _write_ward(wards, "13113", 139.70, 35.65)
    _write_ward(wards, "13103", 139.75, 35.65)
    return wards


def test_store_loads_only_intersecting_wards(ward_root: Path):
    store = BuildingStore(ward_root)
    bbox = (139.699, 35.649, 139.705, 35.652)
    index = store.buildings_in_bbox(bbox)
    assert len(index.select(bbox)) == 1
    geom = index.select(bbox)[0][0]
    assert shape(geom).centroid.x < 139.71


def test_store_expands_bbox_with_margin(ward_root: Path):
    store = BuildingStore(ward_root)
    bbox = (139.699, 35.649, 139.701, 35.651)
    without = store.buildings_in_bbox(bbox, margin_m=0)
    with_margin = store.buildings_in_bbox(bbox, margin_m=5000)
    assert len(without.select(bbox)) == 1
    assert len(with_margin.select(expand_bbox(bbox, 5000))) >= 1


def test_is_tokyo23_layout(tmp_path: Path):
    from hikage_navi.app import is_tokyo23_layout

    assert not is_tokyo23_layout(tmp_path)
    (tmp_path / "boundary.geojson").write_text("{}")
    (tmp_path / "walk-graph.json").write_text("{}")
    (tmp_path / "wards").mkdir()
    assert is_tokyo23_layout(tmp_path)
