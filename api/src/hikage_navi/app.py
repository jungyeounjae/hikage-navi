from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import mapping, shape

from hikage_navi.errors import RouteError
from hikage_navi.graph import load_walk_graph
from hikage_navi.schemas import PathDto, RouteRequest, RouteResponse, WaterSpotDto
from hikage_navi.service import plan_routes
from hikage_navi.shadows import BuildingIndex, ShadowIndex, shadow_margin_m
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


def data_dir() -> Path:
    env = os.environ.get("HIKAGE_DATA_DIR")
    if env:
        return Path(env)
    processed = ROOT / "data/processed"
    if (processed / "shibuya-walk-graph.json").exists():
        return processed
    return ROOT / "data/fixtures"


def load_ctx():
    d = data_dir()
    graph = load_walk_graph(d / "shibuya-walk-graph.json")
    boundary = shape(json.loads((d / "shibuya-boundary.geojson").read_text())["geometry"])
    buildings_raw = json.loads((d / "shibuya-buildings.geojson").read_text())
    buildings = BuildingIndex(
        [
            (shape(f["geometry"]), float(f["properties"]["height"]))
            for f in buildings_raw["features"]
        ]
    )
    water_spots = load_water_spots(d / "shibuya-water-spots.geojson")
    return graph, boundary, buildings, water_spots


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


def create_app() -> FastAPI:
    app = FastAPI()
    # Local Vite + Vercel preview/production (*.vercel.app). Extra origins: CORS_ORIGINS=comma-separated.
    extra = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=extra,
        allow_origin_regex=r"https://.*\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    graph, boundary, buildings, water_spots = load_ctx()
    rendered: dict[tuple, object] = {}

    def shadow_geometry(alt: float, az: float, window):
        """같은 시각·같은 화면이면 다시 계산하지 않는다 (union이 수 초 걸린다)."""
        key = (round(alt, 1), round(az, 1), tuple(round(v, 4) for v in window))
        if key not in rendered:
            if len(rendered) >= SHADOW_CACHE_SIZE:
                rendered.pop(next(iter(rendered)))
            selected = buildings.select(
                window, margin_m=shadow_margin_m(alt, buildings.max_height_m)
            )
            rendered[key] = ShadowIndex.from_buildings(selected, alt, az).union_lonlat(
                bbox=window
            )
        return rendered[key]

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/boundary")
    def boundary_ep():
        return json.loads((data_dir() / "shibuya-boundary.geojson").read_text())

    @app.get("/shadows")
    def shadows_ep(datetime: str = Query(...), bbox: str | None = Query(None)):
        alt, az = sun_position(datetime_from_iso(datetime))
        if is_night(alt):
            return {"type": "FeatureCollection", "features": [], "night": True}
        window = parse_bbox(bbox) or boundary.bounds
        geom = shadow_geometry(alt, az, window)
        features = (
            []
            if geom.is_empty
            else [{"type": "Feature", "properties": {}, "geometry": mapping(geom)}]
        )
        # 좌표 수십만 개를 FastAPI 기본 인코더에 태우면 응답에만 수 초 걸린다
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
                graph=graph,
                buildings=buildings,
                boundary=boundary,
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
            shortest=_path_dto(result.shortest, water_spots),
            shadiest=_path_dto(result.shadiest, water_spots) if result.shadiest else None,
            same_route=result.same_route,
            long_detour=result.long_detour,
            warning=result.warning,
        )

    return app


def datetime_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


app = create_app()
