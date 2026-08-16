# hikage-navi v0.1 (로컬 앱) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시부야구 안에서 시각을 고르고 출발·도착을 찍으면, 건물 그림자를 지도에 그리고 최단 도보와 그늘 도보를 비교하는 웹+API를 노트북에서 돌린다.

**Architecture:** 브라우저는 MapLibre로 국토지리원 타일만 그리고, 그림자·경로는 FastAPI가 계산한다. 런타임은 전처리된 GeoJSON/그래프 파일을 메모리에 올린다. 테스트와 초기 실행은 `data/fixtures/`의 작은 데이터로 하고, 마지막 전처리 태스크가 실제 시부야 PLATEAU·OSM을 `data/processed/`에 만든다.

**Tech Stack:** Python 3.11+, FastAPI, Shapely, pyproj, NetworkX, suncalc, pytest; TypeScript, React, Vite, MapLibre GL JS, Vitest.

**Spec:** `docs/01-requirements.md`, `docs/02-functional-spec.md`, `docs/03-ui-spec.md`, `docs/04-data-algorithm.md`, `docs/05-acceptance.md`, `docs/06-tech-stack.md`

## Global Constraints

- 대상: 시부야구만. 경계선 위는 안으로 본다.
- UI 문구는 일본어. 사양·커밋·주석은 한국어 가능.
- 타임존: `Asia/Tokyo`. 대표점 태양 위치: lon 139.7016, lat 35.6580.
- 그늘 비용 `α = 3` 고정. 스냅 75 m. 직선 3 km 초과 거절.
- 보행 4.8 km/h. 거리는 m 정수, 시간은 분 올림(0 m면 0분). 그늘%는 0–100 정수 반올림.
- 야간: 태양 고도 ≤ 0°. 고도 < 5°이면 그림자 길이를 `H / tan(5°)`로 캡.
- 평면 좌표: EPSG:6677. 저장·API: EPSG:4326.
- 공개 Nominatim / 공개 OSRM 데모 호출 금지. Next.js·DB·로그인 금지.
- 이 계획은 Docker / Vercel / GCP를 포함하지 않는다. 배포는 별도 계획(`docs/07-gcp-cicd.md`). 로컬 앱이 수용기준 A–E를 통과한 뒤에만 연다.

## File Structure

```
api/
  pyproject.toml
  src/hikage_navi/
    constants.py      # 수치 상수
    geo.py            # 하버사인, 경계, 평면 변환
    sun.py            # 고도·방위·야간·그림자 길이
    shadows.py        # 건물 → 그림자 폴리곤
    graph.py          # 보행 그래프 로드·스냅
    routing.py        # 최단·그늘 다익스트라
    errors.py         # 일본어 오류 코드
    schemas.py        # Pydantic 요청/응답
    service.py        # 검증 + 경로 오케스트레이션
    app.py            # FastAPI
  tests/
    conftest.py
    test_geo.py
    test_sun.py
    test_shadows.py
    test_graph.py
    test_routing.py
    test_service.py
    test_app.py
web/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/main.tsx
  src/copy.ts
  src/types.ts
  src/state.ts
  src/api.ts
  src/App.tsx
  src/TopBar.tsx
  src/MapView.tsx
  src/Panel.tsx
  src/state.test.ts
data/fixtures/
  shibuya-boundary.geojson
  shibuya-buildings.geojson
  shibuya-walk-graph.json
api/scripts/preprocess.py
```

---

### Task 1: Python 패키지와 지리 유틸

**Files:**
- Create: `api/pyproject.toml`
- Create: `api/src/hikage_navi/__init__.py`
- Create: `api/src/hikage_navi/constants.py`
- Create: `api/src/hikage_navi/geo.py`
- Create: `api/tests/test_geo.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `SHIBUYA_LON: float = 139.7016`
  - `SHIBUYA_LAT: float = 35.6580`
  - `ALPHA_SHADE: float = 3.0`
  - `SNAP_MAX_M: float = 75.0`
  - `MAX_STRAIGHT_M: float = 3000.0`
  - `WALK_M_PER_MIN: float = 80.0`  # 4.8 km/h
  - `MIN_SUN_ALTITUDE_DEG: float = 5.0`
  - `PLANAR_CRS: str = "EPSG:6677"`
  - `haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float`
  - `to_planar(lon: float, lat: float) -> tuple[float, float]`
  - `from_planar(x: float, y: float) -> tuple[float, float]`
  - `point_in_boundary(lon: float, lat: float, boundary) -> bool`  # Shapely Polygon, 경계선 위 True

- [x] **Step 1: Write the failing test**

Create `api/tests/test_geo.py`:

```python
from hikage_navi.geo import haversine_m, point_in_boundary, to_planar, from_planar
from shapely.geometry import Polygon, Point


def test_haversine_zero():
    assert haversine_m(139.7016, 35.6580, 139.7016, 35.6580) == 0


def test_haversine_about_111m_per_0_001_deg_lat():
    d = haversine_m(139.7016, 35.6580, 139.7016, 35.6590)
    assert 100 < d < 130


def test_point_on_boundary_is_inside():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    assert point_in_boundary(0.0, 0.0, poly) is True
    assert point_in_boundary(0.5, 0.5, poly) is True
    assert point_in_boundary(2.0, 2.0, poly) is False


def test_planar_roundtrip():
    lon, lat = 139.7016, 35.6580
    x, y = to_planar(lon, lat)
    lon2, lat2 = from_planar(x, y)
    assert abs(lon - lon2) < 1e-7
    assert abs(lat - lat2) < 1e-7
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pytest tests/test_geo.py -v
```

Expected: FAIL — `hikage_navi` not found or functions not defined.

- [x] **Step 3: Write minimal implementation**

`api/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hikage-navi"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "shapely>=2.0",
  "pyproj>=3.6",
  "networkx>=3.3",
  "suncalc>=0.1.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
preprocess = ["geopandas>=1.0", "osmnx>=1.9"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

`api/src/hikage_navi/__init__.py` empty.

`api/src/hikage_navi/constants.py`:

```python
SHIBUYA_LON = 139.7016
SHIBUYA_LAT = 35.6580
ALPHA_SHADE = 3.0
SNAP_MAX_M = 75.0
MAX_STRAIGHT_M = 3000.0
WALK_M_PER_MIN = 80.0
MIN_SUN_ALTITUDE_DEG = 5.0
PLANAR_CRS = "EPSG:6677"
GEOGRAPHIC_CRS = "EPSG:4326"
```

`api/src/hikage_navi/geo.py`:

```python
from math import asin, cos, radians, sin, sqrt

from pyproj import Transformer
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import GEOGRAPHIC_CRS, PLANAR_CRS

_TO_PLANAR = Transformer.from_crs(GEOGRAPHIC_CRS, PLANAR_CRS, always_xy=True)
_FROM_PLANAR = Transformer.from_crs(PLANAR_CRS, GEOGRAPHIC_CRS, always_xy=True)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def to_planar(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TO_PLANAR.transform(lon, lat)
    return float(x), float(y)


def from_planar(x: float, y: float) -> tuple[float, float]:
    lon, lat = _FROM_PLANAR.transform(x, y)
    return float(lon), float(lat)


def point_in_boundary(lon: float, lat: float, boundary: BaseGeometry) -> bool:
    pt = Point(lon, lat)
    return bool(boundary.covers(pt))
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/test_geo.py -v
```

Expected: 4 passed

- [x] **Step 5: Commit**

```bash
git add api/pyproject.toml api/src/hikage_navi/__init__.py api/src/hikage_navi/constants.py api/src/hikage_navi/geo.py api/tests/test_geo.py
git commit -m "feat: 시부야 거리·경계·평면좌표 유틸을 추가한다"
```

---

### Task 2: 태양 위치와 그림자 길이

**Files:**
- Create: `api/src/hikage_navi/sun.py`
- Create: `api/tests/test_sun.py`

**Interfaces:**
- Consumes: `SHIBUYA_LON`, `SHIBUYA_LAT`, `MIN_SUN_ALTITUDE_DEG` from `constants.py`
- Produces:
  - `sun_position(dt) -> tuple[float, float]`  # (altitude_deg, azimuth_deg) 북=0 시계방향. `dt`는 timezone-aware datetime
  - `is_night(altitude_deg: float) -> bool`  # `altitude_deg <= 0`
  - `shadow_length_m(height_m: float, altitude_deg: float) -> float`

- [x] **Step 1: Write the failing test**

`api/tests/test_sun.py`:

```python
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
    from math import tan, radians
    expected = 10.0 / tan(radians(5.0))
    assert abs(shadow_length_m(10.0, 1.0) - expected) < 1e-6
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && . .venv/bin/activate && pytest tests/test_sun.py -v
```

Expected: FAIL — `hikage_navi.sun` not found

- [x] **Step 3: Write minimal implementation**

`api/src/hikage_navi/sun.py`:

```python
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
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/test_sun.py -v
```

Expected: 5 passed. `test_noon_in_august_is_day`의 azimuth 범위가 실패하면 `sun_position`의 +180 보정을 뒤집지 말고, 실제 출력 azimuth를 로그로 확인한 뒤 테스트 범위만 사양(북=0 시계방향, 정오≈남≈180)에 맞게 유지한다. 구현이 남=0을 그대로 두면 안 된다.

- [x] **Step 5: Commit**

```bash
git add api/src/hikage_navi/sun.py api/tests/test_sun.py
git commit -m "feat: 태양 고도·방위와 그림자 길이를 계산한다"
```

---

### Task 3: 건물 그림자 폴리곤

**Files:**
- Create: `api/src/hikage_navi/shadows.py`
- Create: `api/tests/test_shadows.py`

**Interfaces:**
- Consumes: `to_planar`, `from_planar`, `shadow_length_m`
- Produces:
  - `building_shadow(footprint_lonlat, height_m: float, altitude_deg: float, azimuth_deg: float)` → Shapely Polygon (EPSG:4326)
  - `all_shadows(buildings: list[tuple[polygon, float]], altitude_deg: float, azimuth_deg: float)` → Shapely Geometry (union, 4326)

`footprint_lonlat`은 Shapely Polygon (lon, lat). 높이 < 2 m 건물은 `all_shadows`에서 제외.

- [x] **Step 1: Write the failing test**

`api/tests/test_shadows.py`:

```python
from shapely.geometry import Polygon, box

from hikage_navi.shadows import all_shadows, building_shadow


def test_shadow_extends_west_when_sun_is_east():
    # 작은 사각형. 태양 방위 90°=동 → 그림자는 서쪽(경도 감소)
    foot = box(139.7015, 35.6579, 139.7017, 35.6581)
    shadow = building_shadow(foot, height_m=50.0, altitude_deg=45.0, azimuth_deg=90.0)
    assert shadow.bounds[0] < foot.bounds[0]
    assert shadow.covers(foot)


def test_short_building_excluded():
    foot = box(139.7015, 35.6579, 139.7017, 35.6581)
    geom = all_shadows([(foot, 1.5)], altitude_deg=45.0, azimuth_deg=90.0)
    assert geom.is_empty
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && . .venv/bin/activate && pytest tests/test_shadows.py -v
```

Expected: FAIL — module not found

- [x] **Step 3: Write minimal implementation**

`api/src/hikage_navi/shadows.py`:

```python
from math import cos, radians, sin

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from hikage_navi.geo import from_planar, to_planar
from hikage_navi.sun import shadow_length_m


def _to_xy(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda lon, lat: to_planar(lon, lat), geom)


def _to_lonlat(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda x, y: from_planar(x, y), geom)


def building_shadow(
    footprint_lonlat: Polygon,
    height_m: float,
    altitude_deg: float,
    azimuth_deg: float,
) -> Polygon:
    length = shadow_length_m(height_m, altitude_deg)
    # 태양 반대 방향. 북=0 시계방향 → 수학각: 90-az
    math_rad = radians(90.0 - azimuth_deg)
    dx = -length * cos(math_rad)
    dy = -length * sin(math_rad)
    foot_xy = _to_xy(footprint_lonlat)
    roof_xy = transform(lambda x, y: (x + dx, y + dy), foot_xy)
    pts = list(foot_xy.exterior.coords) + list(roof_xy.exterior.coords)
    hull = Polygon(pts).convex_hull
    return _to_lonlat(hull)


def all_shadows(
    buildings: list[tuple[Polygon, float]],
    altitude_deg: float,
    azimuth_deg: float,
) -> BaseGeometry:
    polys = [
        building_shadow(poly, h, altitude_deg, azimuth_deg)
        for poly, h in buildings
        if h >= 2.0
    ]
    if not polys:
        return Polygon()
    return unary_union(polys)
```

`test_shadow_extends_west_when_sun_is_east`가 실패하면 `dx, dy` 부호만 바꿔 태양 반대가 서쪽이 되게 한다. 사양: 꼭짓점을 태양 **반대**로 `L`만큼 이동.

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/test_shadows.py tests/test_sun.py tests/test_geo.py -v
```

Expected: all passed

- [x] **Step 5: Commit**

```bash
git add api/src/hikage_navi/shadows.py api/tests/test_shadows.py
git commit -m "feat: 건물 밑면을 태양 반대 방향으로 투영해 그림자를 만든다"
```

---

### Task 4: 보행 그래프와 75 m 스냅

**Files:**
- Create: `api/src/hikage_navi/graph.py`
- Create: `api/tests/test_graph.py`
- Create: `data/fixtures/shibuya-walk-graph.json`

**Interfaces:**
- Consumes: `haversine_m`, `SNAP_MAX_M`
- Produces:
  - `@dataclass Edge`: `u: int`, `v: int`, `coords: list[tuple[float, float]]`, `length_m: float`
  - `@dataclass WalkGraph`: `nodes: dict[int, tuple[float, float]]`, `edges: list[Edge]`
  - `load_walk_graph(path: Path) -> WalkGraph`
  - `snap_to_node(graph: WalkGraph, lon: float, lat: float) -> tuple[int, float]`
  - `class SnapError(Exception)` — 75 m 초과

JSON 스키마:

```json
{
  "nodes": [{"id": 1, "lon": 139.7016, "lat": 35.6580}],
  "edges": [{"u": 1, "v": 2, "coords": [[139.7016, 35.6580], [139.7020, 35.6582]]}]
}
```

`length_m`은 로드 시 coords 구간 하버사인 합으로 계산한다.

- [x] **Step 1: Write fixture and failing test**

`data/fixtures/shibuya-walk-graph.json`:

```json
{
  "nodes": [
    {"id": 1, "lon": 139.70050, "lat": 35.65900},
    {"id": 2, "lon": 139.70160, "lat": 35.65800},
    {"id": 3, "lon": 139.70270, "lat": 35.65700}
  ],
  "edges": [
    {"u": 1, "v": 2, "coords": [[139.70050, 35.65900], [139.70160, 35.65800]]},
    {"u": 2, "v": 3, "coords": [[139.70160, 35.65800], [139.70270, 35.65700]]}
  ]
}
```

`api/tests/test_graph.py`:

```python
from pathlib import Path

import pytest

from hikage_navi.graph import SnapError, load_walk_graph, snap_to_node

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/shibuya-walk-graph.json"


def test_load_three_nodes():
    g = load_walk_graph(FIXTURE)
    assert set(g.nodes) == {1, 2, 3}
    assert len(g.edges) == 2
    assert g.edges[0].length_m > 0


def test_snap_near_node_2():
    g = load_walk_graph(FIXTURE)
    node_id, dist = snap_to_node(g, 139.70160, 35.65800)
    assert node_id == 2
    assert dist < 1.0


def test_snap_too_far_raises():
    g = load_walk_graph(FIXTURE)
    with pytest.raises(SnapError):
        snap_to_node(g, 139.71000, 35.67000)
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && . .venv/bin/activate && pytest tests/test_graph.py -v
```

Expected: FAIL — module not found

- [x] **Step 3: Write minimal implementation**

`api/src/hikage_navi/graph.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hikage_navi.constants import SNAP_MAX_M
from hikage_navi.geo import haversine_m


class SnapError(Exception):
    pass


@dataclass
class Edge:
    u: int
    v: int
    coords: list[tuple[float, float]]
    length_m: float


@dataclass
class WalkGraph:
    nodes: dict[int, tuple[float, float]]
    edges: list[Edge]


def load_walk_graph(path: Path) -> WalkGraph:
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes = {int(n["id"]): (float(n["lon"]), float(n["lat"])) for n in raw["nodes"]}
    edges: list[Edge] = []
    for e in raw["edges"]:
        coords = [(float(c[0]), float(c[1])) for c in e["coords"]]
        length = 0.0
        for a, b in zip(coords, coords[1:]):
            length += haversine_m(a[0], a[1], b[0], b[1])
        edges.append(Edge(u=int(e["u"]), v=int(e["v"]), coords=coords, length_m=length))
    return WalkGraph(nodes=nodes, edges=edges)


def snap_to_node(graph: WalkGraph, lon: float, lat: float) -> tuple[int, float]:
    best_id = None
    best_d = float("inf")
    for nid, (nlon, nlat) in graph.nodes.items():
        d = haversine_m(lon, lat, nlon, nlat)
        if d < best_d:
            best_d = d
            best_id = nid
    if best_id is None or best_d > SNAP_MAX_M:
        raise SnapError()
    return best_id, best_d
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/test_graph.py -v
```

Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add api/src/hikage_navi/graph.py api/tests/test_graph.py data/fixtures/shibuya-walk-graph.json
git commit -m "feat: 보행 그래프 로드와 75m 스냅을 추가한다"
```

---

### Task 5: 최단·그늘 경로

**Files:**
- Create: `api/src/hikage_navi/routing.py`
- Create: `api/tests/test_routing.py`
- Create: `data/fixtures/shibuya-buildings.geojson`

**Interfaces:**
- Consumes: `WalkGraph`, `Edge`, `all_shadows`, `ALPHA_SHADE`, `WALK_M_PER_MIN`
- Produces:
  - `@dataclass PathResult`: `node_ids: list[int]`, `coords: list[tuple[float, float]]`, `distance_m: int`, `duration_min: int`, `shade_m: int`, `sun_m: int`, `shade_pct: int`
  - `edge_shade_split(edge: Edge, shadows) -> tuple[float, float]`  # D_shade, D_sun
  - `shortest_path(graph: WalkGraph, src: int, dst: int, shadows=None) -> PathResult`
  - `shadiest_path(graph: WalkGraph, src: int, dst: int, shadows) -> PathResult`
  - `class DisconnectedError(Exception)`

`duration_min`: `math.ceil(distance_m / WALK_M_PER_MIN)` 단 `distance_m == 0`이면 0.  
`shade_pct`: `round(100 * shade_m / distance_m)` 단 거리 0이면 0.  
무방향: 각 Edge를 u–v, v–u 둘 다 쓴다.  
최단 `W = length_m`. 그늘 `W = D_shade + 3 * D_sun`.  
주간에는 최단에도 `shadows`를 넘겨 `shade_pct`를 채운다(가중치는 거리만).

- [x] **Step 1: Write the failing test**

`data/fixtures/shibuya-buildings.geojson` — 노드 2 근처 높은 건물 하나:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {"height": 80},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [139.70140, 35.65785],
          [139.70180, 35.65785],
          [139.70180, 35.65815],
          [139.70140, 35.65815],
          [139.70140, 35.65785]
        ]]
      }
    }
  ]
}
```

`api/tests/test_routing.py`:

```python
from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from hikage_navi.graph import load_walk_graph
from hikage_navi.routing import DisconnectedError, edge_shade_split, shortest_path
from hikage_navi.graph import Edge

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/shibuya-walk-graph.json"


def test_full_edge_in_shadow():
    # EPSG:6677은 일본 구역용 — 시부야 근처 좌표로 검증
    coords = [(139.7016, 35.6580), (139.7027, 35.6580)]
    length = haversine_m(*coords[0], *coords[1])
    e = Edge(u=1, v=2, coords=coords, length_m=length)
    shadow = box(139.70, 35.65, 139.71, 35.66)
    d_shade, d_sun = edge_shade_split(e, shadow)
    assert d_shade == pytest.approx(length, rel=0.05)
    assert d_sun == pytest.approx(0.0, abs=5.0)


def test_shortest_1_to_3():
    g = load_walk_graph(FIXTURE)
    result = shortest_path(g, 1, 3)
    assert result.node_ids == [1, 2, 3]
    assert result.distance_m > 0
    assert result.duration_min >= 1
    assert result.shade_pct == 0


def test_disconnected_raises():
    g = load_walk_graph(FIXTURE)
    g.edges = g.edges[:1]
    with pytest.raises(DisconnectedError):
        shortest_path(g, 1, 3)
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && . .venv/bin/activate && pytest tests/test_routing.py -v
```

Expected: FAIL — module not found

- [x] **Step 3: Write minimal implementation**

`api/src/hikage_navi/routing.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from hikage_navi.constants import ALPHA_SHADE, WALK_M_PER_MIN
from hikage_navi.geo import to_planar
from hikage_navi.graph import Edge, WalkGraph


class DisconnectedError(Exception):
    pass


@dataclass
class PathResult:
    node_ids: list[int]
    coords: list[tuple[float, float]]
    distance_m: int
    duration_min: int
    shade_m: int
    sun_m: int
    shade_pct: int


def edge_shade_split(edge: Edge, shadows: BaseGeometry) -> tuple[float, float]:
    if edge.length_m == 0:
        return 0.0, 0.0
    line = LineString(edge.coords)
    line_xy = transform(lambda lon, lat: to_planar(lon, lat), line)
    sh_xy = transform(lambda lon, lat: to_planar(lon, lat), shadows)
    inter = line_xy.intersection(sh_xy)
    d_shade = float(inter.length) if not inter.is_empty else 0.0
    d_shade = min(d_shade, edge.length_m)
    return d_shade, max(0.0, edge.length_m - d_shade)


def _metrics(graph: WalkGraph, node_ids: list[int], shadows: BaseGeometry | None) -> PathResult:
    coords: list[tuple[float, float]] = []
    dist = 0.0
    shade = 0.0
    for a, b in zip(node_ids, node_ids[1:]):
        edge = next(e for e in graph.edges if {e.u, e.v} == {a, b})
        part = edge.coords if edge.u == a else list(reversed(edge.coords))
        if coords:
            part = part[1:]
        coords.extend(part)
        dist += edge.length_m
        if shadows is None:
            d_shade, _ = 0.0, edge.length_m
        else:
            d_shade, _ = edge_shade_split(edge, shadows)
        shade += d_shade
    sun = max(0.0, dist - shade)
    distance_m = int(round(dist))
    if distance_m == 0:
        duration_min = 0
        shade_pct = 0
    else:
        duration_min = math.ceil(distance_m / WALK_M_PER_MIN)
        shade_pct = int(round(100 * shade / dist))
    return PathResult(
        node_ids=node_ids,
        coords=coords,
        distance_m=distance_m,
        duration_min=duration_min,
        shade_m=int(round(shade)),
        sun_m=int(round(sun)),
        shade_pct=shade_pct,
    )


def _nx_graph(graph: WalkGraph, weight_fn) -> nx.Graph:
    G = nx.Graph()
    for nid, (lon, lat) in graph.nodes.items():
        G.add_node(nid, lon=lon, lat=lat)
    for e in graph.edges:
        G.add_edge(e.u, e.v, weight=weight_fn(e), edge=e)
    return G


def _path(graph: WalkGraph, src: int, dst: int, weight_fn, shadows: BaseGeometry | None) -> PathResult:
    G = _nx_graph(graph, weight_fn)
    try:
        nodes = nx.shortest_path(G, src, dst, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise DisconnectedError() from exc
    return _metrics(graph, nodes, shadows)


def shortest_path(graph: WalkGraph, src: int, dst: int) -> PathResult:
    return _path(graph, src, dst, lambda e: e.length_m, shadows=None)


def shadiest_path(graph: WalkGraph, src: int, dst: int, shadows: BaseGeometry) -> PathResult:
    def w(e: Edge) -> float:
        d_shade, d_sun = edge_shade_split(e, shadows)
        return d_shade + ALPHA_SHADE * d_sun

    return _path(graph, src, dst, w, shadows)
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/test_routing.py tests/test_graph.py -v
```

Expected: all passed

- [x] **Step 5: Commit**

```bash
git add api/src/hikage_navi/routing.py api/tests/test_routing.py data/fixtures/shibuya-buildings.geojson
git commit -m "feat: 최단·그늘 가중 다익스트라를 추가한다"
```

---

### Task 6: 경로 서비스와 FastAPI

**Files:**
- Create: `api/src/hikage_navi/errors.py`
- Create: `api/src/hikage_navi/schemas.py`
- Create: `api/src/hikage_navi/service.py`
- Create: `api/src/hikage_navi/app.py`
- Create: `api/tests/conftest.py`
- Create: `api/tests/test_service.py`
- Create: `api/tests/test_app.py`
- Create: `data/fixtures/shibuya-boundary.geojson`

**Interfaces:**
- Consumes: geo, sun, shadows, graph, routing, constants
- Produces:
  - `RouteError(code: str, message: str)` codes: `outside` | `too_far` | `snap` | `disconnected` | `server`
  - `plan_routes(origin, destination, dt, *, graph, buildings, boundary) -> RouteResult`
  - FastAPI: `GET /health`, `POST /routes`, `GET /shadows?datetime=`, `GET /boundary`
  - 오류 HTTP 400 `{ "code": "...", "message": "..." }` 우선순위: outside → too_far → snap → disconnected

일본어 메시지 (그대로):

- outside: `渋谷区内の2点を指定してください`
- too_far: `3km以内で指定してください`
- snap: `歩ける道の近くを選んでください`
- disconnected: `この2点を歩くルートが見つかりません`
- server: `しばらくしてからもう一度お試しください`

`RouteResult` 필드: `night: bool`, `shortest: PathResult`, `shadiest: PathResult | None`, `same_route: bool`, `long_detour: bool` (그늘 거리 > 최단 * 1.5).  
같은 노드 origin==destination → `snap`이 아니라 `disconnected`가 아니라 **outside보다 뒤**, 같은 노드면 `disconnected` 메시지를 쓰지 말고 `snap`과 별도로: 사양은 “같은 노드이면 거절”. `code="same_node"`, 메시지는 `歩ける道の近くを選んでください`가 어색하므로 **same node는 `disconnected`와 같은 문안을 쓰지 않고** `渋谷区内の2点を指定してください`보다 구체적인 새 문안이 사양에 없다. 사양 6.1: “origin과 destination이 같은 노드이면 거절”. 구현: `code="same_node"`, `message="渋谷区内の2点を指定してください"`를 쓰지 말고 `message="3km以内で指定してください"`도 쓰지 말 것. **message=`歩ける道の近くを選んでください`도 아님.** 사용자에게 한 줄: 사양에 문안이 없으므로 `この2点を歩くルートが見つかりません`을 쓴다 (`disconnected`).

직선 3 km는 **스냅 전** 입력 좌표 하버사인.

데이터 디렉터리: 환경변수 `HIKAGE_DATA_DIR`, 기본 `data/processed`, 없으면 `data/fixtures`.

- [x] **Step 1: Write fixtures and failing tests**

`data/fixtures/shibuya-boundary.geojson` — 시부야 대략 bbox (실제 행정경계는 Task 9에서 교체):

```json
{
  "type": "Feature",
  "properties": {},
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [139.680, 35.640],
      [139.720, 35.640],
      [139.720, 35.680],
      [139.680, 35.680],
      [139.680, 35.640]
    ]]
  }
}
```

`api/tests/conftest.py`:

```python
from pathlib import Path

import pytest
from shapely.geometry import shape
import json

from hikage_navi.graph import load_walk_graph

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data/fixtures"


@pytest.fixture
def graph():
    return load_walk_graph(FIX / "shibuya-walk-graph.json")


@pytest.fixture
def boundary():
    raw = json.loads((FIX / "shibuya-boundary.geojson").read_text())
    return shape(raw["geometry"])


@pytest.fixture
def buildings():
    raw = json.loads((FIX / "shibuya-buildings.geojson").read_text())
    out = []
    for f in raw["features"]:
        out.append((shape(f["geometry"]), float(f["properties"]["height"])))
    return out
```

`api/tests/test_service.py`:

```python
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
```

`api/tests/test_app.py`:

```python
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
    assert res.json()["code"] == "outside"
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd api && . .venv/bin/activate && pytest tests/test_service.py tests/test_app.py -v
```

Expected: FAIL — modules not found

- [x] **Step 3: Write minimal implementation**

`api/src/hikage_navi/errors.py`:

```python
class RouteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
```

`api/src/hikage_navi/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


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


class RouteResponse(BaseModel):
    night: bool
    shortest: PathDto
    shadiest: PathDto | None
    same_route: bool
    long_detour: bool
    warning: str | None = None
```

`api/src/hikage_navi/service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shapely.geometry.base import BaseGeometry

from hikage_navi.constants import MAX_STRAIGHT_M
from hikage_navi.errors import RouteError
from hikage_navi.geo import haversine_m, point_in_boundary
from hikage_navi.graph import SnapError, WalkGraph, snap_to_node
from hikage_navi.routing import DisconnectedError, PathResult, shadiest_path, shortest_path
from hikage_navi.shadows import all_shadows
from hikage_navi.sun import is_night, sun_position


@dataclass
class RouteResult:
    night: bool
    shortest: PathResult
    shadiest: PathResult | None
    same_route: bool
    long_detour: bool
    warning: str | None


def plan_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    dt: datetime,
    *,
    graph: WalkGraph,
    buildings: list,
    boundary: BaseGeometry,
) -> RouteResult:
    o_in = point_in_boundary(origin[0], origin[1], boundary)
    d_in = point_in_boundary(destination[0], destination[1], boundary)
    if not o_in or not d_in:
        raise RouteError("outside", "渋谷区内の2点を指定してください")
    if haversine_m(origin[0], origin[1], destination[0], destination[1]) > MAX_STRAIGHT_M:
        raise RouteError("too_far", "3km以内で指定してください")
    try:
        src, _ = snap_to_node(graph, origin[0], origin[1])
        dst, _ = snap_to_node(graph, destination[0], destination[1])
    except SnapError as exc:
        raise RouteError("snap", "歩ける道の近くを選んでください") from exc
    if src == dst:
        raise RouteError("disconnected", "この2点を歩くルートが見つかりません")
    alt, az = sun_position(dt)
    night = is_night(alt)
    shadows = None if night else all_shadows(buildings, alt, az)
    try:
        shortest = shortest_path(graph, src, dst, shadows=shadows)
    except DisconnectedError as exc:
        raise RouteError("disconnected", "この2点を歩くルートが見つかりません") from exc
    if night:
        return RouteResult(
            night=True,
            shortest=shortest,
            shadiest=None,
            same_route=False,
            long_detour=False,
            warning=None,
        )
    shadiest = shadiest_path(graph, src, dst, shadows)
    same = shortest.node_ids == shadiest.node_ids
    long_detour = shadiest.distance_m > int(shortest.distance_m * 1.5)
    warning = None
    if long_detour:
        warning = "日陰ルートは最短より長いです"
    return RouteResult(
        night=False,
        shortest=shortest,
        shadiest=shadiest,
        same_route=same,
        long_detour=long_detour,
        warning=warning,
    )
```

`api/src/hikage_navi/app.py`:

```python
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
            raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"code": "server", "message": "しばらくしてからもう一度お試しください"},
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
```

FastAPI `HTTPException(detail=dict)`는 클라이언트가 `{"detail": {...}}`로 받는다. `test_routes_outside_400`는 `res.json()["detail"]["code"]`를 검사하도록 테스트를 맞춘다.

- [x] **Step 4: Run test to verify it passes**

```bash
cd api && . .venv/bin/activate && pytest tests/ -v
```

Expected: all passed

- [x] **Step 5: Commit**

```bash
git add api/src/hikage_navi/errors.py api/src/hikage_navi/schemas.py api/src/hikage_navi/service.py api/src/hikage_navi/app.py api/tests/conftest.py api/tests/test_service.py api/tests/test_app.py data/fixtures/shibuya-boundary.geojson
git commit -m "feat: 경로 검증과 FastAPI /routes /shadows를 추가한다"
```

---

### Task 7: 웹 상태기계와 일본어 카피

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/copy.ts`
- Create: `web/src/types.ts`
- Create: `web/src/state.ts`
- Create: `web/src/state.test.ts`
- Create: `web/src/App.tsx`

**Interfaces:**
- Consumes: 없음 (API 호출은 Task 8)
- Produces:
  - `copy` 객체 — `docs/03-ui-spec.md` 문안 그대로
  - `reduce(state, action) -> AppState`
  - phases: `S0` `S1` `S2` `S3` `S4` `S5`

- [x] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { initialState, reduce } from "./state";

const origin = { lon: 139.7016, lat: 35.658, inBoundary: true };
const dest = { lon: 139.7027, lat: 35.657, inBoundary: true };

describe("map tap", () => {
  it("S0 tap sets origin and S1", () => {
    const s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    expect(s.phase).toBe("S1");
    expect(s.origin).toEqual(origin);
  });

  it("S1 tap sets destination and S2", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    expect(s.phase).toBe("S2");
    expect(s.destination).toEqual(dest);
  });

  it("reset returns S0", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "RESET" });
    expect(s.phase).toBe("S0");
    expect(s.origin).toBeNull();
  });
});
```

`web/package.json`:

```json
{
  "name": "hikage-navi-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "maplibre-gl": "^4.7.1",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "vitest": "^2.1.4"
  }
}
```

`web/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: "node" },
});
```

- [x] **Step 2: Run test to verify it fails**

```bash
cd web && npm install && npm test
```

Expected: FAIL — `./state` not found

- [x] **Step 3: Write minimal implementation**

`web/src/copy.ts` — 화면사양 문안 그대로:

```ts
export const copy = {
  title: "日陰ナビ",
  subtitle: "渋谷区 · 徒歩",
  nightBadge: "夜間",
  legendShortest: "最短",
  legendShade: "日陰",
  s0: "地図をタップして出発地点を選んでください",
  s0sub: "対象は渋谷区内の徒歩ルートです",
  s1: "出発が決まりました。次に到着地点をタップしてください",
  redoOrigin: "出発をやり直す",
  s2: "出発・到着が決まりました",
  search: "ルートを探す",
  reset: "やり直す",
  sameRoute: "同じルートです",
  longer: (m: number) => `日陰ルートは ${m}m 長いです`,
  muchLonger: "日陰ルートは最短よりかなり長いです",
  nightOnly: "夜間のため日陰ルートはありません",
  loadingMap: "読み込み中",
  loadingRoute: "ルートを計算しています",
  nightShade: "夜間のため日陰を計算しません",
  useLocation: "現在地を出発にする",
  close: "閉じる",
  outsideHint: "渋谷区内の2点を指定してください",
  attribution:
    "地図: 国土地理院 / 建物: Project PLATEAU（国土交通省） / 道路: © OpenStreetMap contributors / 対象: 渋谷区 · 徒歩のみ",
  errors: {
    outside: "渋谷区内の2点を指定してください",
    too_far: "3km以内で指定してください",
    snap: "歩ける道の近くを選んでください",
    disconnected: "この2点を歩くルートが見つかりません",
    server: "しばらくしてからもう一度お試しください",
  },
};
```

`web/src/types.ts`:

```ts
export type Phase = "S0" | "S1" | "S2" | "S3" | "S4" | "S5";

export type Pin = { lon: number; lat: number; inBoundary: boolean };

export type PathDto = {
  coordinates: [number, number][];
  distance_m: number;
  duration_min: number;
  shade_m: number;
  sun_m: number;
  shade_pct: number;
};

export type RouteResponse = {
  night: boolean;
  shortest: PathDto;
  shadiest: PathDto | null;
  same_route: boolean;
  long_detour: boolean;
  warning: string | null;
};

export type AppState = {
  phase: Phase;
  origin: Pin | null;
  destination: Pin | null;
  datetimeLocal: string;
  route: RouteResponse | null;
  errorMessage: string | null;
  selected: "shortest" | "shadiest";
};

export type Action =
  | { type: "MAP_TAP"; point: Pin }
  | { type: "RESET" }
  | { type: "RESET_ORIGIN" }
  | { type: "SET_DATETIME"; value: string }
  | { type: "ROUTE_OK"; route: RouteResponse }
  | { type: "ROUTE_ERR"; message: string }
  | { type: "CLEAR_ERROR" }
  | { type: "SELECT"; which: "shortest" | "shadiest" }
  | { type: "SET_ORIGIN"; point: Pin };
```

`web/src/state.ts`:

```ts
import type { Action, AppState } from "./types";

function nowLocalInput(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function initialState(): AppState {
  return {
    phase: "S0",
    origin: null,
    destination: null,
    datetimeLocal: nowLocalInput(),
    route: null,
    errorMessage: null,
    selected: "shadiest",
  };
}

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "MAP_TAP": {
      if (state.phase === "S0" || state.phase === "S1" && !state.origin) {
        return { ...state, origin: action.point, destination: null, route: null, phase: "S1", errorMessage: null };
      }
      if (state.phase === "S1") {
        return { ...state, destination: action.point, route: null, phase: "S2", errorMessage: null };
      }
      return { ...state, destination: action.point, route: null, phase: "S2", errorMessage: null };
    }
    case "SET_ORIGIN":
      return {
        ...state,
        origin: action.point,
        phase: state.destination ? "S2" : "S1",
        route: null,
        errorMessage: null,
      };
    case "RESET":
      return { ...initialState(), datetimeLocal: state.datetimeLocal };
    case "RESET_ORIGIN":
      return { ...state, origin: null, destination: null, route: null, phase: "S0", errorMessage: null };
    case "SET_DATETIME":
      return { ...state, datetimeLocal: action.value };
    case "ROUTE_OK": {
      const night = action.route.night;
      const selected = night || action.route.same_route ? "shortest" : "shadiest";
      return {
        ...state,
        route: action.route,
        phase: night ? "S4" : "S3",
        selected,
        errorMessage: null,
      };
    }
    case "ROUTE_ERR":
      return { ...state, phase: "S5", errorMessage: action.message, route: null };
    case "CLEAR_ERROR":
      return { ...state, phase: state.destination ? "S2" : state.origin ? "S1" : "S0", errorMessage: null };
    case "SELECT":
      return { ...state, selected: action.which };
    default:
      return state;
  }
}
```

`web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`는 상태와 `copy.title`만 화면에 그리는 최소 셸. MapLibre는 Task 8.

`web/src/App.tsx`:

```tsx
import { useReducer } from "react";
import { copy } from "./copy";
import { initialState, reduce } from "./state";

export function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  return (
    <div>
      <header>
        <h1>{copy.title}</h1>
        <p>{copy.subtitle}</p>
        <p>{state.phase}</p>
      </header>
      <p>{copy.attribution}</p>
    </div>
  );
}
```

`web/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`web/index.html`:

```html
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>日陰ナビ</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd web && npm test
```

Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add web/
git commit -m "feat: 웹 상태기계와 일본어 카피를 추가한다"
```

---

### Task 8: 지도·API 연결 (로컬 완성)

**Files:**
- Create: `web/src/api.ts`
- Create: `web/src/TopBar.tsx`
- Create: `web/src/MapView.tsx`
- Create: `web/src/Panel.tsx`
- Modify: `web/src/App.tsx`
- Create: `web/src/styles.css`

**Interfaces:**
- Consumes: `reduce`, `copy`, FastAPI `http://localhost:8000`
- Produces: 단일 화면. GSI 타일 `https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png`. 초기 center `[139.7016, 35.6580]` zoom 15. pitch/bearing 0. 탭은 click(싱글). `/boundary` 라인, `/shadows` 면, `/routes` 선.

- [x] **Step 1: Write api client (no placeholder)**

`web/src/api.ts`:

```ts
import type { PathDto, Pin, RouteResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchBoundary(): Promise<GeoJSON.GeoJSON> {
  const res = await fetch(`${BASE}/boundary`);
  return res.json();
}

export async function fetchShadows(iso: string): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${BASE}/shadows?datetime=${encodeURIComponent(iso)}`);
  return res.json();
}

export async function postRoutes(
  origin: Pin,
  destination: Pin,
  iso: string,
): Promise<RouteResponse> {
  const res = await fetch(`${BASE}/routes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: { lon: origin.lon, lat: origin.lat },
      destination: { lon: destination.lon, lat: destination.lat },
      datetime: iso,
    }),
  });
  const body = await res.json();
  if (!res.ok) {
    const message = body?.detail?.message ?? body?.message ?? "しばらくしてからもう一度お試しください";
    throw new Error(message);
  }
  return body as RouteResponse;
}

export function localInputToIso(local: string): string {
  return `${local}:00+09:00`;
}

export function formatPath(p: PathDto): string {
  return `${p.distance_m}m · ${p.duration_min}分 · 日陰 ${p.shade_pct}%`;
}
```

- [x] **Step 2: Implement MapView, TopBar, Panel, App**

`MapView.tsx` 요구:

- `new maplibregl.Map({ style: { version: 8, sources: { gsi: { type: "raster", tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"], tileSize: 256, attribution: "国土地理院" } }, layers: [{ id: "gsi", type: "raster", source: "gsi" }] }, center: [139.7016, 35.6580], zoom: 15, pitch: 0, bearing: 0, interactive: true })`
- `map.dragRotate.disable(); map.touchZoomRotate.disableRotation();`
- `map.on("click", (e) => onTap(e.lngLat.lng, e.lngLat.lat))` — dblclick 줌은 기본, 핀은 click만
- boundary GeoJSON source `boundary`, line layer
- shadows fill layer, night이면 source data empty
- origin/destination Marker 라벨 `出発` / `到着`. `inBoundary===false`이면 회색
- shortest line `#1d4ed8`, shadiest `#b45309` 위에. `same_route`이면 한 선
- 범례 HTML `最短` / `日陰`

`TopBar.tsx`: `copy.title`, `copy.subtitle`, datetime `input type="datetime-local"`, night이면 `copy.nightBadge`.

`Panel.tsx`: phase별 `copy` 문안. S2에서 탐색 버튼이 API를 호출. S3 카드 탭 → `SELECT`. S5 `copy.close` → `CLEAR_ERROR` (핀 유지). 현재지 버튼: `navigator.geolocation.getCurrentPosition`, 구 밖이면 `outsideHint`.

`App.tsx`: datetime 변경 시 phase가 S3/S4이면 같은 origin/destination으로 `postRoutes` 재호출.

경로 계산 중 버튼 disabled, 텍스트 `copy.loadingRoute`.

- [x] **Step 3: Run API + web locally**

터미널 1:

```bash
cd api && . .venv/bin/activate && uvicorn hikage_navi.app:app --reload --port 8000
```

Expected: `Uvicorn running on http://127.0.0.1:8000`

터미널 2:

```bash
cd web && npm run dev
```

Expected: `Local: http://localhost:5173/`

브라우저에서 지도가 보이고, 픽스처 경계 안에서 두 점을 찍고 경로가 나온다.

- [x] **Step 4: Run automated tests**

```bash
cd api && . .venv/bin/activate && pytest tests/ -v
cd web && npm test && npm run build
```

Expected: pytest all passed, vitest passed, tsc+vite build success

- [x] **Step 5: Commit**

```bash
git add web/src/
git commit -m "feat: 지도와 경로 API를 한 화면에 연결한다"
```

---

### Task 9: 시부야 실데이터 전처리

**Files:**
- Create: `api/scripts/preprocess.py`
- Create: `api/scripts/README.md`

**Interfaces:**
- Consumes: 동일한 파일명 `shibuya-boundary.geojson`, `shibuya-buildings.geojson` (`properties.height`), `shibuya-walk-graph.json`
- Produces: `data/processed/` 에 위 세 파일. 원본은 `data/raw/` (gitignore).

이 태스크가 끝나야 수용기준 C(하치코–요요기)를 실도로에서 검증할 수 있다. 픽스처만으로는 하치코 경로가 없다.

- [ ] **Step 1: Write preprocess script**

`api/scripts/preprocess.py`는 다음을 수행한다.

1. `data/raw/` 생성
2. 시부야 경계: OSM Overpass 또는 `osmnx.geocode_to_gdf("Shibuya, Tokyo, Japan")` → `shibuya-boundary.geojson` (Polygon)
3. 건물: PLATEAU 渋谷区 `13113` CityGML LOD1을 받아 GeoJSON으로 변환. `measuredHeight` → `properties.height`. 경계와 교차, `height >= 2`
4. 보행망: Geofabrik `https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf`를 받아 경계로 clip. `osmnx.graph_from_polygon(..., network_type="walk")` 후 노드/엣지를 `shibuya-walk-graph.json`으로 저장. `foot=no` 제외는 osmnx walk 프로파일이 담당
5. 결과를 `data/processed/`에 기록

스크립트 상단 주석에 실행:

```bash
cd api && . .venv/bin/activate && pip install -e ".[preprocess]"
python scripts/preprocess.py
```

공개 Nominatim 데모에 대량 경로 요청을 보내지 말 것. `geocode_to_gdf` 한 번은 허용(경계 폴리곤). 보행 그래프는 로컬 PBF에서 만든다.

- [ ] **Step 2: Run script**

```bash
cd api && . .venv/bin/activate && python scripts/preprocess.py
```

Expected: `data/processed/shibuya-walk-graph.json` 존재, 노드 수 > 1000, 건물 Feature > 1000

- [ ] **Step 3: Point API at processed data and smoke-test**

```bash
export HIKAGE_DATA_DIR=/Users/yeounjaejung/hikage-navi/data/processed
cd api && . .venv/bin/activate && uvicorn hikage_navi.app:app --port 8000
```

하치코 근처 `139.7005, 35.6590` 부근과 요요기공원 동쪽 `139.7023, 35.6710`이 구 안·3km인지 확인 후 POST `/routes`. 구 밖이면 요요기 대신 에비스 `139.7100, 35.6467`을 쓴다(수용기준 C).

- [ ] **Step 4: Commit script only, not raw/processed**

```bash
git add api/scripts/preprocess.py api/scripts/README.md
git commit -m "feat: 시부야 PLATEAU·OSM 전처리 스크립트를 추가한다"
```

`data/raw`, `data/processed`는 커밋하지 않는다.

---

### Task 10: 수용기준 수동 통과

**Files:**
- Modify: `docs/05-acceptance.md` 체크박스를 실행 기록으로 채우지 말고, 검증 좌표를 문서 주석이 아니라 `docs/superpowers/plans/2026-08-14-hikage-navi-v0.1.md` 이 섹션에만 적는다. 스펙 파일은 체크리스트로 남긴다.

**Interfaces:**
- Consumes: 로컬 웹+API+processed 데이터
- Produces: 수용기준 A–E 통과. F(전철·계정)가 제품에 없음.

- [ ] **Step 1: Start stack**

```bash
# terminal 1
export HIKAGE_DATA_DIR=/Users/yeounjaejung/hikage-navi/data/processed
cd /Users/yeounjaejung/hikage-navi/api && . .venv/bin/activate && uvicorn hikage_navi.app:app --port 8000
# terminal 2
cd /Users/yeounjaejung/hikage-navi/web && npm run dev
```

- [ ] **Step 2: Walk docs/05-acceptance.md A–E**

고정 점(처리 후 스냅이 되면 그대로, 실패하면 75 m 안 보도로 1회만 조정):

- 출발: 139.70056, 35.65905 (하치코 출구 부근)
- 도착: 139.7024, 35.6712 (요요기공원 동쪽) — 구 밖/3 km 초과면 139.7104, 35.6467 (에비스)

확인: 주간 두 경로, 그늘%, 10:00 vs 16:00 그림자 방향, 야간 그늘 없음, 구 밖 거절 문안, 3 km 거절, 스냅 실패 문안, 새로고침 시 핀 소실, 로그인 없음, 출처 표시, Nominatim/OSRM 네트워크 탭에 없음, UI 일본어.

- [ ] **Step 3: Run full automated suite once more**

```bash
cd /Users/yeounjaejung/hikage-navi/api && . .venv/bin/activate && pytest tests/ -v
cd /Users/yeounjaejung/hikage-navi/web && npm test && npm run build
```

Expected: all passed

- [ ] **Step 4: Commit nothing unless copy/bugfix files changed**

버그 수정이 있으면 해당 파일만 커밋. 수정이 없으면 커밋하지 않는다.

---

## Out of this plan

다음 계획은 `docs/07-gcp-cicd.md`를 구현한다. 포함하지 말 것: `Dockerfile.api`, `cloudbuild.yaml`, Vercel 프로젝트, Artifact Registry.

백로그(장소 검색, 가로수, 대중교통)도 이 계획에 넣지 않는다.

## Spec coverage (self-review)

| 요건 | Task |
| --- | --- |
| R1 지도 GSI | 8 |
| R2 시각 | 7, 8 |
| R3 건물 그림자 | 2, 3, 6, 8 |
| R4 출발·도착·현재지 | 4, 7, 8 |
| R5 두 경로 | 5, 6, 8 |
| R6 지표 | 5, 8 |
| R7 야간 | 2, 6, 8 |
| R8 구 밖 | 1, 6, 8 |
| 3 km / 75 m / α=3 | 4, 5, 6 |
| F7 출처 | 7, 8 |
| 수용 A–E | 10 |
| 전처리 | 9 |
| 배포 GCP/Vercel | 제외 (별도 계획) |
