from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import MAX_STRAIGHT_M
from hikage_navi.errors import RouteError
from hikage_navi.geo import bbox_of, expand_bbox, haversine_m, point_in_boundary
from hikage_navi.graph import SnapError, WalkGraph, snap_to_node, subgraph_in_bbox
from hikage_navi.routing import (
    DisconnectedError,
    PathResult,
    path_metrics,
    shadiest_path,
    shortest_path,
)
from hikage_navi.shadows import BuildingIndex, ShadowIndex, shadow_margin_m
from hikage_navi.sun import is_night, sun_position
from hikage_navi.wards import OUTSIDE_MESSAGE


DETOUR_MARGIN_M = 300.0


def _area_around(graph: WalkGraph, bbox, src: int, dst: int) -> WalkGraph:
    """탐색 범위를 좁힌다. 구 전체를 매번 계산하면 응답이 십수 초로 늘어난다."""
    area = subgraph_in_bbox(graph, expand_bbox(bbox, DETOUR_MARGIN_M))
    if src in area.nodes and dst in area.nodes:
        return area
    return graph


def _shadows_in(buildings, bbox, altitude_deg: float, azimuth_deg: float) -> ShadowIndex:
    index = buildings if isinstance(buildings, BuildingIndex) else BuildingIndex(buildings)
    margin = shadow_margin_m(altitude_deg, index.max_height_m)
    return ShadowIndex.from_buildings(
        index.select(bbox, margin_m=margin), altitude_deg, azimuth_deg
    )


@dataclass
class RouteResult:
    night: bool
    shortest: PathResult
    shadiest: PathResult | None
    same_route: bool
    long_detour: bool
    warning: str | None


def plan_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    dt: datetime,
    *,
    graph: WalkGraph,
    buildings: list,
    boundary: BaseGeometry,
) -> RouteResult:
    o_in = point_in_boundary(origin[0], origin[1], boundary)
    d_in = point_in_boundary(destination[0], destination[1], boundary)
    if not o_in or not d_in:
        raise RouteError("outside", OUTSIDE_MESSAGE)
    if haversine_m(origin[0], origin[1], destination[0], destination[1]) > MAX_STRAIGHT_M:
        raise RouteError("too_far", "3km以内で指定してください")
    try:
        src, _ = snap_to_node(graph, origin[0], origin[1])
        dst, _ = snap_to_node(graph, destination[0], destination[1])
    except SnapError as exc:
        raise RouteError("snap", "歩ける道の近くを選んでください") from exc
    if src == dst:
        raise RouteError("disconnected", "この2点を歩くルートが見つかりません")
    alt, az = sun_position(dt)
    night = is_night(alt)
    search_area = _area_around(graph, bbox_of([origin, destination]), src, dst)
    try:
        shortest = shortest_path(search_area, src, dst)
    except DisconnectedError as exc:
        raise RouteError("disconnected", "この2点を歩くルートが見つかりません") from exc
    if night:
        return RouteResult(
            night=True,
            shortest=shortest,
            shadiest=None,
            same_route=False,
            long_detour=False,
            warning=None,
        )
    # 최단 경로 주변만 계산한다. 우회 상한(1.5배) 안에서 후보는 이 안에 들어온다
    corridor = expand_bbox(bbox_of(shortest.coords), DETOUR_MARGIN_M)
    shadows = _shadows_in(buildings, corridor, alt, az)
    area = _area_around(graph, bbox_of(shortest.coords), src, dst)
    shortest = path_metrics(area, shortest.node_ids, shadows)
    shadiest = shadiest_path(area, src, dst, shadows)
    same = shortest.node_ids == shadiest.node_ids
    long_detour = shadiest.distance_m > int(shortest.distance_m * 1.5)
    warning = None
    if long_detour:
        warning = "日陰ルートは最短より長いです"
    return RouteResult(
        night=False,
        shortest=shortest,
        shadiest=shadiest,
        same_route=same,
        long_detour=long_detour,
        warning=warning,
    )
