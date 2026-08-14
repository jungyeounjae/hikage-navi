from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from hikage_navi.errors import RouteError
from hikage_navi.service import plan_routes

JST = ZoneInfo("Asia/Tokyo")
DAY = datetime(2026, 8, 14, 12, 0, tzinfo=JST)
NIGHT = datetime(2026, 8, 14, 0, 0, tzinfo=JST)


def test_day_returns_two_paths(graph, buildings, boundary):
    r = plan_routes(
        (139.70050, 35.65900),
        (139.70270, 35.65700),
        DAY,
        graph=graph,
        buildings=buildings,
        boundary=boundary,
    )
    assert r.night is False
    assert r.shortest is not None
    assert r.shadiest is not None
    assert r.shortest.distance_m <= r.shadiest.distance_m
    assert 0 <= r.shortest.shade_pct <= 100


def test_night_has_no_shadiest(graph, buildings, boundary):
    r = plan_routes(
        (139.70050, 35.65900),
        (139.70270, 35.65700),
        NIGHT,
        graph=graph,
        buildings=buildings,
        boundary=boundary,
    )
    assert r.night is True
    assert r.shadiest is None


def test_outside_raises(graph, buildings, boundary):
    with pytest.raises(RouteError) as ei:
        plan_routes(
            (139.0, 35.0),
            (139.70270, 35.65700),
            DAY,
            graph=graph,
            buildings=buildings,
            boundary=boundary,
        )
    assert ei.value.code == "outside"
    assert ei.value.message == "渋谷区内の2点を指定してください"
