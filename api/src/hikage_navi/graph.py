from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path

from hikage_navi.constants import SNAP_GRID_CELL_M, SNAP_MAX_M
from hikage_navi.geo import haversine_m, to_planar


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
    adj: dict[int, list[tuple[int, Edge]]] | None = field(default=None, repr=False)
    _cells: dict[tuple[int, int], list[int]] | None = field(default=None, repr=False)
    _cell_m: float | None = field(default=None, repr=False)


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
    graph = WalkGraph(nodes=nodes, edges=edges)
    build_snap_index(graph)
    build_adjacency(graph)
    return graph


def subgraph_in_bbox(graph: WalkGraph, bbox: tuple[float, float, float, float]) -> WalkGraph:
    """양 끝점이 bbox 안에 있는 간선만 남긴다."""
    min_lon, min_lat, max_lon, max_lat = bbox
    nodes = {
        nid: (lon, lat)
        for nid, (lon, lat) in graph.nodes.items()
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
    }
    edges = [e for e in graph.edges if e.u in nodes and e.v in nodes]
    area = WalkGraph(nodes=nodes, edges=edges)
    build_adjacency(area)
    return area


def build_adjacency(graph: WalkGraph) -> None:
    adj: dict[int, list[tuple[int, Edge]]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges:
        if edge.u in adj and edge.v in adj:
            adj[edge.u].append((edge.v, edge))
            adj[edge.v].append((edge.u, edge))
    graph.adj = adj


def build_snap_index(graph: WalkGraph, cell_m: float = SNAP_GRID_CELL_M) -> None:
    cells: dict[tuple[int, int], list[int]] = {}
    for nid, (lon, lat) in graph.nodes.items():
        x, y = to_planar(lon, lat)
        key = (int(x // cell_m), int(y // cell_m))
        cells.setdefault(key, []).append(nid)
    graph._cells = cells
    graph._cell_m = cell_m


def snap_to_node(graph: WalkGraph, lon: float, lat: float) -> tuple[int, float]:
    cells = getattr(graph, "_cells", None)
    if not cells:
        candidates = graph.nodes.keys()
    else:
        cell_m = getattr(graph, "_cell_m", SNAP_GRID_CELL_M)
        x, y = to_planar(lon, lat)
        cx, cy = int(x // cell_m), int(y // cell_m)
        ring = int(ceil(SNAP_MAX_M / cell_m)) + 1
        candidates = []
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                candidates.extend(cells.get((cx + dx, cy + dy), ()))
    best_id = None
    best_d = float("inf")
    for nid in candidates:
        nlon, nlat = graph.nodes[nid]
        d = haversine_m(lon, lat, nlon, nlat)
        if d < best_d or (d == best_d and (best_id is None or nid < best_id)):
            best_d = d
            best_id = nid
    if best_id is None or best_d > SNAP_MAX_M:
        raise SnapError()
    return best_id, best_d
