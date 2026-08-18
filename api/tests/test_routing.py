from pathlib import Path

import pytest
from shapely.geometry import box

from hikage_navi.geo import haversine_m
from hikage_navi.graph import Edge, load_walk_graph
from hikage_navi.routing import (
    DisconnectedError,
    edge_shade_split,
    shadiest_path,
    shortest_path,
)
from hikage_navi.shadows import ShadowIndex

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/shibuya-walk-graph.json"


def test_full_edge_in_shadow():
    # EPSG:6677은 일본 구역용 — 시부야 근처 좌표로 검증
    coords = [(139.7016, 35.6580), (139.7027, 35.6580)]
    length = haversine_m(*coords[0], *coords[1])
    e = Edge(u=1, v=2, coords=coords, length_m=length)
    shadow = box(139.70, 35.65, 139.71, 35.66)
    d_shade, d_sun = edge_shade_split(e, shadow)
    assert d_shade == pytest.approx(length, rel=0.05)
    assert d_sun == pytest.approx(0.0, abs=5.0)


def test_shortest_1_to_3():
    g = load_walk_graph(FIXTURE)
    result = shortest_path(g, 1, 3)
    assert result.node_ids == [1, 2, 3]
    assert result.distance_m > 0
    assert result.duration_min >= 1
    assert result.shade_pct == 0


def test_shortest_without_shadows_has_zero_continuous_sun():
    g = load_walk_graph(FIXTURE)
    result = shortest_path(g, 1, 3)
    assert result.max_continuous_sun_m == 0
    assert result.max_continuous_sun_seconds == 0


def test_shortest_with_shadows_reports_continuous_sun():
    g = load_walk_graph(FIXTURE)
    shadow = box(139.7010, 35.6575, 139.7030, 35.6590)
    result = shortest_path(g, 1, 3, shadows=shadow)
    assert result.max_continuous_sun_m >= 0
    assert result.max_continuous_sun_seconds == int(
        round(result.max_continuous_sun_m / 80.0 * 60)
    )


def test_shortest_reports_shade_when_shadows_given():
    g = load_walk_graph(FIXTURE)
    # 픽스처 노드 1–2–3 주변을 덮는 그림자 → 최단도 그늘%를 채운다
    shadow = box(139.7010, 35.6575, 139.7030, 35.6590)
    result = shortest_path(g, 1, 3, shadows=shadow)
    assert result.node_ids == [1, 2, 3]
    assert result.shade_pct > 0
    assert result.shade_m > 0


def test_shade_split_accepts_shadow_index():
    coords = [(139.7016, 35.6580), (139.7027, 35.6580)]
    e = Edge(u=1, v=2, coords=coords, length_m=haversine_m(*coords[0], *coords[1]))
    shadow = box(139.70, 35.65, 139.7020, 35.66)
    from_geom = edge_shade_split(e, shadow)
    from_index = edge_shade_split(e, ShadowIndex.from_geometry(shadow))
    assert from_index[0] == pytest.approx(from_geom[0], abs=5.0)
    assert from_index[1] == pytest.approx(from_geom[1], abs=5.0)


def test_shadiest_accepts_shadow_index():
    g = load_walk_graph(FIXTURE)
    index = ShadowIndex.from_geometry(box(139.7010, 35.6575, 139.7030, 35.6590))
    result = shadiest_path(g, 1, 3, index)
    assert result.node_ids == [1, 2, 3]
    assert result.shade_pct > 0


def test_disconnected_raises():
    g = load_walk_graph(FIXTURE)
    g.edges = g.edges[:1]
    with pytest.raises(DisconnectedError):
        shortest_path(g, 1, 3)
