from shapely.geometry import box

from hikage_navi.shadows import all_shadows, building_shadow


def test_shadow_extends_west_when_sun_is_east():
    # 작은 사각형. 태양 방위 90°=동 → 그림자는 서쪽(경도 감소)
    foot = box(139.7015, 35.6579, 139.7017, 35.6581)
    shadow = building_shadow(foot, height_m=50.0, altitude_deg=45.0, azimuth_deg=90.0)
    assert shadow.bounds[0] < foot.bounds[0]
    assert shadow.covers(foot)


def test_short_building_excluded():
    foot = box(139.7015, 35.6579, 139.7017, 35.6581)
    geom = all_shadows([(foot, 1.5)], altitude_deg=45.0, azimuth_deg=90.0)
    assert geom.is_empty
