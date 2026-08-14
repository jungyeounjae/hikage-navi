from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from hikage_navi.constants import ALPHA_SHADE, WALK_M_PER_MIN
from hikage_navi.geo import to_planar
from hikage_navi.graph import Edge, WalkGraph


class DisconnectedError(Exception):
    pass


@dataclass
class PathResult:
    node_ids: list[int]
    coords: list[tuple[float, float]]
    distance_m: int
    duration_min: int
    shade_m: int
    sun_m: int
    shade_pct: int


def edge_shade_split(edge: Edge, shadows: BaseGeometry) -> tuple[float, float]:
    if edge.length_m == 0:
        return 0.0, 0.0
    line = LineString(edge.coords)
    line_xy = transform(lambda lon, lat: to_planar(lon, lat), line)
    sh_xy = transform(lambda lon, lat: to_planar(lon, lat), shadows)
    inter = line_xy.intersection(sh_xy)
    d_shade = float(inter.length) if not inter.is_empty else 0.0
    d_shade = min(d_shade, edge.length_m)
    return d_shade, max(0.0, edge.length_m - d_shade)


def _metrics(
    graph: WalkGraph, node_ids: list[int], shadows: BaseGeometry | None
) -> PathResult:
    coords: list[tuple[float, float]] = []
    dist = 0.0
    shade = 0.0
    for a, b in zip(node_ids, node_ids[1:]):
        edge = next(e for e in graph.edges if {e.u, e.v} == {a, b})
        part = edge.coords if edge.u == a else list(reversed(edge.coords))
        if coords:
            part = part[1:]
        coords.extend(part)
        dist += edge.length_m
        if shadows is None:
            d_shade = 0.0
        else:
            d_shade, _ = edge_shade_split(edge, shadows)
        shade += d_shade
    sun = max(0.0, dist - shade)
    distance_m = int(round(dist))
    if distance_m == 0:
        duration_min = 0
        shade_pct = 0
    else:
        duration_min = math.ceil(distance_m / WALK_M_PER_MIN)
        shade_pct = int(round(100 * shade / dist))
    return PathResult(
        node_ids=node_ids,
        coords=coords,
        distance_m=distance_m,
        duration_min=duration_min,
        shade_m=int(round(shade)),
        sun_m=int(round(sun)),
        shade_pct=shade_pct,
    )


def _nx_graph(graph: WalkGraph, weight_fn) -> nx.Graph:
    G = nx.Graph()
    for nid, (lon, lat) in graph.nodes.items():
        G.add_node(nid, lon=lon, lat=lat)
    for e in graph.edges:
        G.add_edge(e.u, e.v, weight=weight_fn(e), edge=e)
    return G


def _path(
    graph: WalkGraph,
    src: int,
    dst: int,
    weight_fn,
    shadows: BaseGeometry | None,
) -> PathResult:
    G = _nx_graph(graph, weight_fn)
    try:
        nodes = nx.shortest_path(G, src, dst, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise DisconnectedError() from exc
    return _metrics(graph, nodes, shadows)


def shortest_path(graph: WalkGraph, src: int, dst: int) -> PathResult:
    return _path(graph, src, dst, lambda e: e.length_m, shadows=None)


def shadiest_path(
    graph: WalkGraph, src: int, dst: int, shadows: BaseGeometry
) -> PathResult:
    def w(e: Edge) -> float:
        d_shade, d_sun = edge_shade_split(e, shadows)
        return d_shade + ALPHA_SHADE * d_sun

    return _path(graph, src, dst, w, shadows)
