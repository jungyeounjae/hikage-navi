from datetime import datetime
from zoneinfo import ZoneInfo

from hikage_navi.sun import is_night, shadow_length_m, sun_position

JST = ZoneInfo("Asia/Tokyo")


def test_noon_in_august_is_day():
    alt, az = sun_position(datetime(2026, 8, 14, 12, 0, tzinfo=JST))
    assert alt > 0
    assert 90 < az < 270


def test_midnight_is_night():
    alt, _az = sun_position(datetime(2026, 8, 14, 0, 0, tzinfo=JST))
    assert is_night(alt) is True


def test_is_night_at_zero_altitude():
    assert is_night(0.0) is True
    assert is_night(0.1) is False


def test_shadow_length_45deg():
    assert abs(shadow_length_m(10.0, 45.0) - 10.0) < 1e-6


def test_shadow_length_capped_below_5deg():
    from math import radians, tan

    expected = 10.0 / tan(radians(5.0))
    assert abs(shadow_length_m(10.0, 1.0) - expected) < 1e-6
