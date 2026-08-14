from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import mapping, shape

from hikage_navi.errors import RouteError
from hikage_navi.graph import load_walk_graph
from hikage_navi.schemas import PathDto, RouteRequest, RouteResponse
from hikage_navi.service import plan_routes
from hikage_navi.shadows import all_shadows
from hikage_navi.sun import is_night, sun_position

ROOT = Path(__file__).resolve().parents[3]


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
    buildings = [
        (shape(f["geometry"]), float(f["properties"]["height"]))
        for f in buildings_raw["features"]
    ]
    return graph, boundary, buildings


def _path_dto(p) -> PathDto:
    return PathDto(
        coordinates=[[c[0], c[1]] for c in p.coords],
        distance_m=p.distance_m,
        duration_min=p.duration_min,
        shade_m=p.shade_m,
        sun_m=p.sun_m,
        shade_pct=p.shade_pct,
    )


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    graph, boundary, buildings = load_ctx()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/boundary")
    def boundary_ep():
        return json.loads((data_dir() / "shibuya-boundary.geojson").read_text())

    @app.get("/shadows")
    def shadows_ep(datetime: str = Query(...)):
        dt = datetime_from_iso(datetime)
        alt, az = sun_position(dt)
        if is_night(alt):
            return {"type": "FeatureCollection", "features": [], "night": True}
        geom = all_shadows(buildings, alt, az)
        return {
            "type": "FeatureCollection",
            "night": False,
            "features": [
                {"type": "Feature", "properties": {}, "geometry": mapping(geom)}
            ],
        }

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
            shortest=_path_dto(result.shortest),
            shadiest=_path_dto(result.shadiest) if result.shadiest else None,
            same_route=result.same_route,
            long_detour=result.long_detour,
            warning=result.warning,
        )

    return app


def datetime_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


app = create_app()
