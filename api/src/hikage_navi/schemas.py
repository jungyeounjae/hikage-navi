from datetime import datetime

from pydantic import BaseModel


class LonLat(BaseModel):
    lon: float
    lat: float


class RouteRequest(BaseModel):
    origin: LonLat
    destination: LonLat
    datetime: datetime


class PathDto(BaseModel):
    coordinates: list[list[float]]
    distance_m: int
    duration_min: int
    shade_m: int
    sun_m: int
    shade_pct: int
    max_continuous_sun_m: int
    max_continuous_sun_seconds: int


class RouteResponse(BaseModel):
    night: bool
    shortest: PathDto
    shadiest: PathDto | None
    same_route: bool
    long_detour: bool
    warning: str | None = None
