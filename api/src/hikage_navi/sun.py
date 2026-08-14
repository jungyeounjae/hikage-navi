from datetime import datetime
from math import radians, tan

from suncalc import get_position

from hikage_navi.constants import MIN_SUN_ALTITUDE_DEG, SHIBUYA_LAT, SHIBUYA_LON


def sun_position(dt: datetime) -> tuple[float, float]:
    pos = get_position(dt, SHIBUYA_LON, SHIBUYA_LAT)
    altitude_deg = float(pos["altitude"]) * 180.0 / 3.141592653589793
    # suncalc azimuth: 남=0, 서=90. 사양: 북=0 시계방향.
    azimuth_from_south_deg = float(pos["azimuth"]) * 180.0 / 3.141592653589793
    azimuth_deg = (azimuth_from_south_deg + 180.0) % 360.0
    return altitude_deg, azimuth_deg


def is_night(altitude_deg: float) -> bool:
    return altitude_deg <= 0.0


def shadow_length_m(height_m: float, altitude_deg: float) -> float:
    alt = max(altitude_deg, MIN_SUN_ALTITUDE_DEG)
    return height_m / tan(radians(alt))
