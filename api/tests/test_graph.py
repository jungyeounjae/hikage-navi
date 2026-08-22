import json
from pathlib import Path

import pytest

from hikage_navi.graph import (
    SnapError,
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


def test_subgraph_keeps_everything_when_bbox_covers_all():
    g = load_walk_graph(FIXTURE)
    whole = subgraph_in_bbox(g, (139.60, 35.60, 139.80, 35.70))
    assert set(whole.nodes) == set(g.nodes)
    assert len(whole.edges) == len(g.edges)


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
