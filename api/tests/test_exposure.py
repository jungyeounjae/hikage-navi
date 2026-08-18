import pytest

from hikage_navi.constants import WALK_M_PER_MIN
from hikage_navi.exposure import max_run_sun_m, sun_seconds
from hikage_navi.geo import from_planar, to_planar
from hikage_navi.shadows import SAMPLE_STEP_M, ShadowIndex
from shapely.geometry import box


def test_all_shade_is_zero():
    assert max_run_sun_m([True, True, True], [5.0, 5.0, 5.0]) == 0.0


def test_all_sun_is_full_length():
    assert max_run_sun_m([False, False, False], [5.0, 5.0, 5.0]) == 15.0


def test_first_sun_run_wins():
    # SUN SUN SHADE SUN
    assert max_run_sun_m([False, False, True, False], [5, 5, 5, 5]) == 10.0


def test_second_sun_run_wins():
    # SUN SHADE SUN SUN SUN
    assert max_run_sun_m([False, True, False, False, False], [5, 5, 5, 5, 5]) == 15.0


def test_shade_resets_between_suns():
    # SUN SHADE SUN SHADE SUN
    assert max_run_sun_m([False, True, False, True, False], [5, 5, 5, 5, 5]) == 5.0


def test_sun_seconds_reuses_walk_speed():
    assert sun_seconds(24.0) == int(round(24.0 / WALK_M_PER_MIN * 60))
    assert sun_seconds(24.0) == 18


def test_index_max_sun_crosses_edge_boundary():
    """한 폴리라인 = Edge A+B. 양 끝만 그늘이면 가운데 SUN이 한 런."""
    start = (139.7016, 35.6580)
    x, y = to_planar(*start)
    # 샘플 수 ceil(L/5)가 6이 되도록 평면 길이를 5 m의 정수배로 고정
    end = from_planar(x + 6 * SAMPLE_STEP_M, y)
    coords = [start, end]
    # 선의 양 끝 ~1/6만 덮는 상자 두 개 → 가운데는 SUN
    xs = [c[0] for c in coords]
    minx, maxx = min(xs), max(xs)
    span = maxx - minx
    left = box(minx - 0.001, 35.6575, minx + span / 6, 35.6585)
    right = box(maxx - span / 6, 35.6575, maxx + 0.001, 35.6585)
    index = ShadowIndex.from_geometry(left.union(right))
    # 샘플 6개라면 SHADE SUN SUN SUN SUN SHADE → 연속 SUN 4 * ~5 m
    got = index.max_continuous_sun_m(coords)
    assert got == pytest.approx(4 * SAMPLE_STEP_M, abs=SAMPLE_STEP_M)
