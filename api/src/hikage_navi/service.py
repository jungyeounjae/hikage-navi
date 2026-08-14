from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import MAX_STRAIGHT_M
from hikage_navi.errors import RouteError
from hikage_navi.geo import haversine_m, point_in_boundary
from hikage_navi.graph import SnapError, WalkGraph, snap_to_node
from hikage_navi.routing import DisconnectedError, PathResult, shadiest_path, shortest_path
from hikage_navi.shadows import all_shadows
from hikage_navi.sun import is_night, sun_position


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
        raise RouteError("outside", "渋谷区内の2点を指定してください")
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
    shadows = None if night else all_shadows(buildings, alt, az)
    try:
        shortest = shortest_path(graph, src, dst, shadows=shadows)
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
    shadiest = shadiest_path(graph, src, dst, shadows)
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
