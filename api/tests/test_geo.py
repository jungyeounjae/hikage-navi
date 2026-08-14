from hikage_navi.geo import from_planar, haversine_m, point_in_boundary, to_planar
from shapely.geometry import Polygon


def test_haversine_zero():
    assert haversine_m(139.7016, 35.6580, 139.7016, 35.6580) == 0


def test_haversine_about_111m_per_0_001_deg_lat():
    d = haversine_m(139.7016, 35.6580, 139.7016, 35.6590)
    assert 100 < d < 130


def test_point_on_boundary_is_inside():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    assert point_in_boundary(0.0, 0.0, poly) is True
    assert point_in_boundary(0.5, 0.5, poly) is True
    assert point_in_boundary(2.0, 2.0, poly) is False


def test_planar_roundtrip():
    lon, lat = 139.7016, 35.6580
    x, y = to_planar(lon, lat)
    lon2, lat2 = from_planar(x, y)
    assert abs(lon - lon2) < 1e-7
    assert abs(lat - lat2) < 1e-7
