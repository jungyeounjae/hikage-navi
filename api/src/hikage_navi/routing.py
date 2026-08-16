from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import ALPHA_SHADE, WALK_M_PER_MIN
from hikage_navi.graph import Edge, WalkGraph
from hikage_navi.shadows import ShadowIndex


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


Shadows = BaseGeometry | ShadowIndex | None
Pair = frozenset


def _as_index(shadows: Shadows) -> ShadowIndex | None:
    if shadows is None or isinstance(shadows, ShadowIndex):
        return shadows
    return ShadowIndex.from_geometry(shadows)


def _shade_map(edges: list[Edge], index: ShadowIndex | None) -> dict[Pair, float]:
    if index is None or index.is_empty or not edges:
        return {}
    lengths = index.shade_lengths([e.coords for e in edges])
    return {
        frozenset((e.u, e.v)): min(float(d), e.length_m)
        for e, d in zip(edges, lengths)
    }


def _split(edge: Edge, shade_map: dict[Pair, float]) -> tuple[float, float]:
    if edge.length_m == 0:
        return 0.0, 0.0
    d_shade = shade_map.get(frozenset((edge.u, edge.v)), 0.0)
    return d_shade, max(0.0, edge.length_m - d_shade)


def edge_shade_split(edge: Edge, shadows: Shadows) -> tuple[float, float]:
    return _split(edge, _shade_map([edge], _as_index(shadows)))


def _metrics(graph: WalkGraph, node_ids: list[int], shade_map: dict[Pair, float]) -> PathResult:
    by_pair = {frozenset((e.u, e.v)): e for e in graph.edges}
    coords: list[tuple[float, float]] = []
    dist = 0.0
    shade = 0.0
    for a, b in zip(node_ids, node_ids[1:]):
        edge = by_pair[frozenset((a, b))]
        part = edge.coords if edge.u == a else list(reversed(edge.coords))
        if coords:
            part = part[1:]
        coords.extend(part)
        dist += edge.length_m
        d_shade, _ = _split(edge, shade_map)
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
    shade_map: dict[Pair, float],
) -> PathResult:
    G = _nx_graph(graph, weight_fn)
    try:
        nodes = nx.shortest_path(G, src, dst, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise DisconnectedError() from exc
    return _metrics(graph, nodes, shade_map)


def path_metrics(graph: WalkGraph, node_ids: list[int], shadows: Shadows) -> PathResult:
    """이미 정해진 경로의 그늘 지표만 다시 계산한다."""
    index = _as_index(shadows)
    on_path = {frozenset(pair) for pair in zip(node_ids, node_ids[1:])}
    edges = [e for e in graph.edges if frozenset((e.u, e.v)) in on_path]
    return _metrics(graph, node_ids, _shade_map(edges, index))


def shortest_path(
    graph: WalkGraph,
    src: int,
    dst: int,
    shadows: Shadows = None,
) -> PathResult:
    result = _path(graph, src, dst, lambda e: e.length_m, {})
    if shadows is None:
        return result
    return path_metrics(graph, result.node_ids, shadows)


def shadiest_path(graph: WalkGraph, src: int, dst: int, shadows: Shadows) -> PathResult:
    shade_map = _shade_map(graph.edges, _as_index(shadows))

    def w(e: Edge) -> float:
        d_shade, d_sun = _split(e, shade_map)
        return d_shade + ALPHA_SHADE * d_sun

    return _path(graph, src, dst, w, shade_map)
