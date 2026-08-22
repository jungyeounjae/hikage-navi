import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import networkx as nx
import pytest

PREPROCESS_PATH = Path(__file__).resolve().parents[1] / "scripts/preprocess.py"
SPEC = spec_from_file_location("preprocess", PREPROCESS_PATH)
assert SPEC is not None and SPEC.loader is not None
PREPROCESS = module_from_spec(SPEC)
SPEC.loader.exec_module(PREPROCESS)


def test_graph_to_walk_json_emits_haversine_edge_length(tmp_path):
    graph = nx.Graph()
    graph.add_node("a", x=139.0, y=35.0)
    graph.add_node("b", x=139.001, y=35.0)
    graph.add_edge("a", "b")
    out = tmp_path / "walk-graph.json"

    PREPROCESS._graph_to_walk_json(graph, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["edges"][0]["length_m"] == pytest.approx(91.085551, abs=1e-6)
