from pathlib import Path

from hikage_navi.constants import WATER_BUFFER_M
from hikage_navi.water import load_water_spots, nearby_water_spots, spot_from_properties

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data/fixtures"
ROUTE = [(139.70050, 35.65900), (139.70160, 35.65800), (139.70270, 35.65700)]


def test_maps_osm_tags_without_inventing_name():
    spot = spot_from_properties(
        {
            "id": "n1",
            "name": None,
            "amenity": "drinking_water",
            "bottle": "yes",
            "access": "yes",
            "opening_hours": "09:00-18:00",
        },
        lon=139.7,
        lat=35.65,
    )
    assert spot.name is None
    assert spot.bottle_refill is True
    assert spot.source == "OSM"
    assert spot.type == "DRINKING_WATER"


def test_buffer_constant_is_50():
    assert WATER_BUFFER_M == 50.0


def test_includes_spot_within_buffer():
    spots = load_water_spots(FIXTURE_DIR / "shibuya-water-spots.geojson")
    found = nearby_water_spots(spots, ROUTE)
    ids = {s.id for s in found}
    assert "osm-near" in ids
    near = next(s for s in found if s.id == "osm-near")
    assert near.route_distance_m <= 50


def test_excludes_spot_beyond_buffer():
    spots = load_water_spots(FIXTURE_DIR / "shibuya-water-spots.geojson")
    ids = {s.id for s in nearby_water_spots(spots, ROUTE)}
    assert "osm-far" not in ids


def test_empty_spots_returns_empty():
    assert nearby_water_spots([], ROUTE) == []


def test_missing_file_loads_empty(tmp_path):
    assert load_water_spots(tmp_path / "none.geojson") == []


def test_bottle_yes_sets_refill_keeps_drinking_water_type():
    spots = load_water_spots(FIXTURE_DIR / "shibuya-water-spots.geojson")
    far = next(s for s in spots if s.id == "osm-far")
    assert far.bottle_refill is True
    assert far.type == "DRINKING_WATER"
    near = next(s for s in spots if s.id == "osm-near")
    assert near.bottle_refill is None
    assert near.type == "DRINKING_WATER"
