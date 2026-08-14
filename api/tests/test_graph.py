from pathlib import Path

import pytest

from hikage_navi.graph import SnapError, load_walk_graph, snap_to_node

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
