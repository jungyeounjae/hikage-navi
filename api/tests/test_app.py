import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).resolve().parents[2] / "data/fixtures"


@pytest.fixture(scope="module")
def client():
    # 실데이터(processed)가 있으면 로딩만 십수 초 걸린다. 테스트는 픽스처로 고정
    os.environ["HIKAGE_DATA_DIR"] = str(FIXTURES)
    from hikage_navi.app import create_app

    with TestClient(create_app()) as c:
        yield c
    os.environ.pop("HIKAGE_DATA_DIR", None)


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_routes_include_max_continuous_sun_fields(client):
    res = client.post(
        "/routes",
        json={
            "origin": {"lon": 139.70050, "lat": 35.65900},
            "destination": {"lon": 139.70270, "lat": 35.65700},
            "datetime": "2026-08-14T12:00:00+09:00",
        },
    )
    assert res.status_code == 200
    body = res.json()["shortest"]
    assert "max_continuous_sun_m" in body
    assert "max_continuous_sun_seconds" in body
    assert isinstance(body["max_continuous_sun_m"], int)
    assert isinstance(body["max_continuous_sun_seconds"], int)


def test_routes_water_spots_only_near_path(client):
    res = client.post(
        "/routes",
        json={
            "origin": {"lon": 139.70050, "lat": 35.65900},
            "destination": {"lon": 139.70270, "lat": 35.65700},
            "datetime": "2026-08-14T12:00:00+09:00",
        },
    )
    assert res.status_code == 200
    spots = res.json()["shortest"]["water_spots"]
    ids = {s["id"] for s in spots}
    assert "osm-near" in ids
    assert "osm-far" not in ids
    assert spots[0]["route_distance_m"] <= 50
    assert "name" in spots[0]


def test_routes_outside_400(client):
    res = client.post(
        "/routes",
        json={
            "origin": {"lon": 139.0, "lat": 35.0},
            "destination": {"lon": 139.70, "lat": 35.66},
            "datetime": "2026-08-14T12:00:00+09:00",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "outside"


def test_shadows_night_is_empty(client):
    res = client.get("/shadows", params={"datetime": "2026-08-14T02:00:00+09:00"})
    assert res.status_code == 200
    assert res.json() == {"type": "FeatureCollection", "features": [], "night": True}


def test_shadows_bbox_excludes_far_area(client):
    params = {"datetime": "2026-08-14T12:00:00+09:00"}
    full = client.get("/shadows", params=params).json()
    assert full["night"] is False
    assert full["features"]
    far = client.get(
        "/shadows", params={**params, "bbox": "139.80,35.60,139.81,35.61"}
    ).json()
    assert far["features"] == []


def test_shadows_rejects_broken_bbox(client):
    res = client.get(
        "/shadows", params={"datetime": "2026-08-14T12:00:00+09:00", "bbox": "1,2,3"}
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "bbox"
