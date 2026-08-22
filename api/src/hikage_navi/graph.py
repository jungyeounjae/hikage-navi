from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hikage_navi.constants import SNAP_MAX_M
from hikage_navi.geo import haversine_m


class SnapError(Exception):
    pass


@dataclass
class Edge:
    u: int
    v: int
    coords: list[tuple[float, float]]
    length_m: float


@dataclass
class WalkGraph:
    nodes: dict[int, tuple[float, float]]
    edges: list[Edge]


def load_walk_graph(path: Path) -> WalkGraph:
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes = {int(n["id"]): (float(n["lon"]), float(n["lat"])) for n in raw["nodes"]}
    edges: list[Edge] = []
    for e in raw["edges"]:
        coords = [(float(c[0]), float(c[1])) for c in e["coords"]]
        if "length_m" in e and e["length_m"] is not None:
            length = float(e["length_m"])
        else:
            length = 0.0
            for a, b in zip(coords, coords[1:]):
                length += haversine_m(a[0], a[1], b[0], b[1])
        edges.append(Edge(u=int(e["u"]), v=int(e["v"]), coords=coords, length_m=length))
    return WalkGraph(nodes=nodes, edges=edges)


def subgraph_in_bbox(graph: WalkGraph, bbox: tuple[float, float, float, float]) -> WalkGraph:
    """양 끝점이 bbox 안에 있는 간선만 남긴다."""
    min_lon, min_lat, max_lon, max_lat = bbox
    nodes = {
        nid: (lon, lat)
        for nid, (lon, lat) in graph.nodes.items()
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
    }
    edges = [e for e in graph.edges if e.u in nodes and e.v in nodes]
    return WalkGraph(nodes=nodes, edges=edges)


def snap_to_node(graph: WalkGraph, lon: float, lat: float) -> tuple[int, float]:
    best_id = None
    best_d = float("inf")
    for nid, (nlon, nlat) in graph.nodes.items():
        d = haversine_m(lon, lat, nlon, nlat)
        if d < best_d:
            best_d = d
            best_id = nid
    if best_id is None or best_d > SNAP_MAX_M:
        raise SnapError()
    return best_id, best_d
