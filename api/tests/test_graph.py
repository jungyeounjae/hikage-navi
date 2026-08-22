import json
from pathlib import Path

import pytest

from hikage_navi.graph import (
    SnapError,
    build_snap_index,
    load_walk_graph,
    snap_to_node,
    subgraph_in_bbox,
)

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/shibuya-walk-graph.json"


def test_load_three_nodes():
    g = load_walk_graph(FIXTURE)
    assert set(g.nodes) == {1, 2, 3}
    assert len(g.edges) == 2
    assert g.edges[0].length_m > 0


def test_snap_near_node_2():
    g = load_walk_graph(FIXTURE)
    node_id, dist = snap_to_node(g, 139.70160, 35.65800)
    assert node_id == 2
    assert dist < 1.0


def test_snap_matches_bruteforce_on_fixture():
    g = load_walk_graph(FIXTURE)
    build_snap_index(g)
    for lon, lat in [(139.70160, 35.65800), (139.70155, 35.65890), (139.70265, 35.65710)]:
        try:
            a, da = snap_to_node(g, lon, lat)
            indexed = (a, round(da, 6))
        except SnapError:
            indexed = None
        cells = g._cells
        g._cells = None
        try:
            b, db = snap_to_node(g, lon, lat)
            brute = (b, round(db, 6))
        except SnapError:
            brute = None
        g._cells = cells
        assert indexed == brute


def test_snap_tie_prefers_smaller_node_id(tmp_path: Path):
    payload = {
        "nodes": [
            {"id": 10, "lon": 139.7016, "lat": 35.6580},
            {"id": 2, "lon": 139.7016, "lat": 35.6580},
        ],
        "edges": [],
    }
    path = tmp_path / "tie.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    build_snap_index(g)
    nid, dist = snap_to_node(g, 139.7016, 35.6580)
    assert nid == 2
    assert dist == 0.0


def test_snap_too_far_raises():
    g = load_walk_graph(FIXTURE)
    with pytest.raises(SnapError):
        snap_to_node(g, 139.71000, 35.67000)


def test_subgraph_keeps_only_edges_inside_bbox():
    g = load_walk_graph(FIXTURE)
    lon2, lat2 = g.nodes[2]
    tiny = subgraph_in_bbox(g, (lon2 - 1e-5, lat2 - 1e-5, lon2 + 1e-5, lat2 + 1e-5))
    assert set(tiny.nodes) == {2}
    assert tiny.edges == []
    assert tiny.adj == {2: []}


def test_subgraph_keeps_everything_when_bbox_covers_all():
    g = load_walk_graph(FIXTURE)
    whole = subgraph_in_bbox(g, (139.60, 35.60, 139.80, 35.70))
    assert set(whole.nodes) == set(g.nodes)
    assert len(whole.edges) == len(g.edges)
    assert whole.adj is not None
    assert [neighbor for neighbor, _ in whole.adj[2]] == [1, 3]


def test_load_uses_length_m_when_present(tmp_path: Path):
    payload = {
        "nodes": [{"id": 1, "lon": 139.0, "lat": 35.0}, {"id": 2, "lon": 139.1, "lat": 35.0}],
        "edges": [
            {
                "u": 1,
                "v": 2,
                "coords": [[139.0, 35.0], [139.1, 35.0]],
                "length_m": 12.5,
            }
        ],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    assert g.edges[0].length_m == 12.5


def test_load_computes_length_when_missing(tmp_path: Path):
    payload = {
        "nodes": [{"id": 1, "lon": 139.7016, "lat": 35.6580}, {"id": 2, "lon": 139.7027, "lat": 35.6580}],
        "edges": [{"u": 1, "v": 2, "coords": [[139.7016, 35.6580], [139.7027, 35.6580]]}],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    assert g.edges[0].length_m > 50.0
