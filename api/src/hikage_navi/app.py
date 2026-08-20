from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import mapping, shape

from hikage_navi.building_store import BuildingStore
from hikage_navi.errors import RouteError
from hikage_navi.graph import load_walk_graph
from hikage_navi.schemas import PathDto, RouteRequest, RouteResponse, WaterSpotDto
from hikage_navi.service import plan_routes
from hikage_navi.shadows import (
    BuildingIndex,
    MAX_SHADOW_MARGIN_M,
    ShadowIndex,
    shadow_margin_m,
)
from hikage_navi.sun import is_night, sun_position
from hikage_navi.water import load_water_spots, nearby_water_spots

ROOT = Path(__file__).resolve().parents[3]
SHADOW_CACHE_SIZE = 8


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(v) for v in value.split(",")]
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail={"code": "bbox", "message": "bbox=minLon,minLat,maxLon,maxLat"},
        )
    return parts[0], parts[1], parts[2], parts[3]


def is_tokyo23_layout(d: Path) -> bool:
    return (
        (d / "boundary.geojson").is_file()
        and (d / "walk-graph.json").is_file()
        and (d / "wards").is_dir()
    )


def data_dir() -> Path:
    env = os.environ.get("HIKAGE_DATA_DIR")
    if env:
        return Path(env)
    processed = ROOT / "data/processed"
    if is_tokyo23_layout(processed / "tokyo23"):
        return processed / "tokyo23"
    if (processed / "shibuya-walk-graph.json").exists():
        return processed
    return ROOT / "data/fixtures"


def _load_water_for(d: Path) -> list:
    for name in ("water-spots.geojson", "shibuya-water-spots.geojson"):
        path = d / name
        if path.is_file():
            return load_water_spots(path)
    parent = d.parent / "shibuya-water-spots.geojson"
    if parent.is_file():
        return load_water_spots(parent)
    fallback = d / "shibuya-water-spots.geojson"
    if fallback.is_file():
        return load_water_spots(fallback)
    return []


@dataclass
class AppContext:
    graph: object
    boundary: object
    buildings: BuildingIndex | BuildingStore
    water_spots: list
    boundary_json_path: Path
    layout: str


def load_ctx() -> AppContext:
    d = data_dir()
    if is_tokyo23_layout(d):
        graph = load_walk_graph(d / "walk-graph.json")
        boundary = shape(
            json.loads((d / "boundary.geojson").read_text(encoding="utf-8"))["geometry"]
        )
        buildings: BuildingIndex | BuildingStore = BuildingStore(d / "wards")
        water_spots = _load_water_for(d)
        return AppContext(
            graph=graph,
            boundary=boundary,
            buildings=buildings,
            water_spots=water_spots,
            boundary_json_path=d / "boundary.geojson",
            layout="tokyo23",
        )
    graph = load_walk_graph(d / "shibuya-walk-graph.json")
    boundary = shape(
        json.loads((d / "shibuya-boundary.geojson").read_text(encoding="utf-8"))["geometry"]
    )
    buildings_raw = json.loads(
        (d / "shibuya-buildings.geojson").read_text(encoding="utf-8")
    )
    buildings = BuildingIndex(
        [
            (shape(f["geometry"]), float(f["properties"]["height"]))
            for f in buildings_raw["features"]
        ]
    )
    water_spots = _load_water_for(d)
    return AppContext(
        graph=graph,
        boundary=boundary,
        buildings=buildings,
        water_spots=water_spots,
        boundary_json_path=d / "shibuya-boundary.geojson",
        layout="shibuya",
    )


def _path_dto(p, spots) -> PathDto:
    matches = nearby_water_spots(spots, p.coords) if p.coords else []
    return PathDto(
        coordinates=[[c[0], c[1]] for c in p.coords],
        distance_m=p.distance_m,
        duration_min=p.duration_min,
        shade_m=p.shade_m,
        sun_m=p.sun_m,
        shade_pct=p.shade_pct,
        max_continuous_sun_m=p.max_continuous_sun_m,
        max_continuous_sun_seconds=p.max_continuous_sun_seconds,
        water_spots=[
            WaterSpotDto(
                id=m.id,
                name=m.name,
                lat=m.lat,
                lon=m.lon,
                type=m.type,
                source=m.source,
                bottle_refill=m.bottle_refill,
                access=m.access,
                opening_hours=m.opening_hours,
                route_distance_m=m.route_distance_m,
            )
            for m in matches
        ],
    )


def _select_buildings(
    buildings: BuildingIndex | BuildingStore,
    window: tuple[float, float, float, float],
    alt: float,
) -> list:
    if isinstance(buildings, BuildingStore):
        pre = buildings.buildings_in_bbox(window, margin_m=MAX_SHADOW_MARGIN_M)
        margin = shadow_margin_m(alt, pre.max_height_m)
        return pre.select(window, margin_m=margin)
    margin = shadow_margin_m(alt, buildings.max_height_m)
    return buildings.select(window, margin_m=margin)


def create_app() -> FastAPI:
    app = FastAPI()
    extra = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=extra,
        allow_origin_regex=r"https://.*\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ctx = load_ctx()
    rendered: dict[tuple, object] = {}

    def shadow_geometry(alt: float, az: float, window):
        key = (round(alt, 1), round(az, 1), tuple(round(v, 4) for v in window))
        if key not in rendered:
            if len(rendered) >= SHADOW_CACHE_SIZE:
                rendered.pop(next(iter(rendered)))
            selected = _select_buildings(ctx.buildings, window, alt)
            rendered[key] = ShadowIndex.from_buildings(selected, alt, az).union_lonlat(
                bbox=window
            )
        return rendered[key]

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/boundary")
    def boundary_ep():
        return json.loads(ctx.boundary_json_path.read_text(encoding="utf-8"))

    @app.get("/shadows")
    def shadows_ep(datetime: str = Query(...), bbox: str | None = Query(None)):
        alt, az = sun_position(datetime_from_iso(datetime))
        if is_night(alt):
            return {"type": "FeatureCollection", "features": [], "night": True}
        window = parse_bbox(bbox) or ctx.boundary.bounds
        geom = shadow_geometry(alt, az, window)
        features = (
            []
            if geom.is_empty
            else [{"type": "Feature", "properties": {}, "geometry": mapping(geom)}]
        )
        return Response(
            content=json.dumps(
                {"type": "FeatureCollection", "night": False, "features": features}
            ),
            media_type="application/json",
        )

    @app.post("/routes", response_model=RouteResponse)
    def routes(req: RouteRequest):
        try:
            result = plan_routes(
                (req.origin.lon, req.origin.lat),
                (req.destination.lon, req.destination.lat),
                req.datetime,
                graph=ctx.graph,
                buildings=ctx.buildings,
                boundary=ctx.boundary,
            )
        except RouteError as exc:
            raise HTTPException(
                status_code=400, detail={"code": exc.code, "message": exc.message}
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "server",
                    "message": "しばらくしてからもう一度お試しください",
                },
            ) from exc
        return RouteResponse(
            night=result.night,
            shortest=_path_dto(result.shortest, ctx.water_spots),
            shadiest=_path_dto(result.shadiest, ctx.water_spots) if result.shadiest else None,
            same_route=result.same_route,
            long_detour=result.long_detour,
            warning=result.warning,
        )

    return app


def datetime_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


app = create_app()
