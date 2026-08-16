from shapely.geometry import LineString, box
from shapely.ops import transform

from hikage_navi.geo import to_planar
from hikage_navi.shadows import (
    SAMPLE_STEP_M,
    BuildingIndex,
    ShadowIndex,
    all_shadows,
    building_shadow,
    shadow_margin_m,
)

FOOT = box(139.7015, 35.6579, 139.7017, 35.6581)
LINE = [(139.7000, 35.6580), (139.7020, 35.6580)]


def _planar_shade_len(coords, geom) -> float:
    line_xy = transform(to_planar, LineString(coords))
    sh_xy = transform(to_planar, geom)
    return float(line_xy.intersection(sh_xy).length)


def test_shadow_extends_west_when_sun_is_east():
    # 작은 사각형. 태양 방위 90°=동 → 그림자는 서쪽(경도 감소)
    shadow = building_shadow(FOOT, height_m=50.0, altitude_deg=45.0, azimuth_deg=90.0)
    assert shadow.bounds[0] < FOOT.bounds[0]
    assert shadow.covers(FOOT)


def test_short_building_excluded():
    geom = all_shadows([(FOOT, 1.5)], altitude_deg=45.0, azimuth_deg=90.0)
    assert geom.is_empty


def test_index_shade_length_matches_geometry():
    buildings = [(FOOT, 50.0), (box(139.7018, 35.6579, 139.7019, 35.6581), 20.0)]
    index = ShadowIndex.from_buildings(buildings, 45.0, 90.0)
    expected = _planar_shade_len(LINE, all_shadows(buildings, 45.0, 90.0))
    assert expected > 0
    assert abs(index.shade_length_m(LINE) - expected) <= SAMPLE_STEP_M


def test_index_from_geometry_matches_geometry():
    geom = all_shadows([(FOOT, 50.0)], 45.0, 90.0)
    index = ShadowIndex.from_geometry(geom)
    assert abs(index.shade_length_m(LINE) - _planar_shade_len(LINE, geom)) <= SAMPLE_STEP_M


def test_index_is_empty_when_all_buildings_short():
    index = ShadowIndex.from_buildings([(FOOT, 1.5)], 45.0, 90.0)
    assert index.is_empty
    assert index.shade_length_m(LINE) == 0.0
    assert index.union_lonlat().is_empty


def test_building_index_selects_only_nearby():
    far = box(139.7500, 35.6579, 139.7502, 35.6581)
    index = BuildingIndex([(FOOT, 50.0), (far, 50.0)])
    selected = index.select((139.6990, 35.6570, 139.7030, 35.6590), margin_m=50.0)
    assert [h for _, h in selected] == [50.0]
    assert selected[0][0].equals(FOOT)


def test_building_index_margin_widens_selection():
    near = box(139.7040, 35.6579, 139.7042, 35.6581)  # bbox 동쪽 약 200m
    index = BuildingIndex([(near, 50.0)])
    window = (139.6990, 35.6570, 139.7020, 35.6590)
    assert index.select(window, margin_m=10.0) == []
    assert len(index.select(window, margin_m=400.0)) == 1


def test_shadow_margin_grows_with_low_sun():
    assert shadow_margin_m(60.0, max_height_m=100.0) < shadow_margin_m(
        10.0, max_height_m=100.0
    )


def test_union_lonlat_filters_by_bbox():
    far = box(139.7500, 35.6579, 139.7502, 35.6581)
    index = ShadowIndex.from_buildings([(FOOT, 50.0), (far, 50.0)], 45.0, 90.0)
    everything = index.union_lonlat()
    near = index.union_lonlat(bbox=(139.6990, 35.6570, 139.7030, 35.6590))
    assert not near.is_empty
    assert near.area < everything.area
    assert near.bounds[2] < 139.7100
