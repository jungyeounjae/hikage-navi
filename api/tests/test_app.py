from fastapi.testclient import TestClient

from hikage_navi.app import create_app


def test_health():
    client = TestClient(create_app())
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_routes_outside_400():
    client = TestClient(create_app())
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
