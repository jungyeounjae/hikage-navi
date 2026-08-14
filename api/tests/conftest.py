from pathlib import Path

import json

import pytest
from shapely.geometry import shape

from hikage_navi.graph import load_walk_graph

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data/fixtures"


@pytest.fixture
def graph():
    return load_walk_graph(FIX / "shibuya-walk-graph.json")


@pytest.fixture
def boundary():
    raw = json.loads((FIX / "shibuya-boundary.geojson").read_text())
    return shape(raw["geometry"])


@pytest.fixture
def buildings():
    raw = json.loads((FIX / "shibuya-buildings.geojson").read_text())
    out = []
    for f in raw["features"]:
        out.append((shape(f["geometry"]), float(f["properties"]["height"])))
    return out
