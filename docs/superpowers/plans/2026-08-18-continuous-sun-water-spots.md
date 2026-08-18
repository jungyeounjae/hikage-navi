# 연속 직사광선 + 급수 스팟 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 경로마다 최대 연속 직사광선 거리·시간을 계산해 카드에 보여주고, 선택한 경로 50 m 안의 OSM 급수 스팟만 지도에 표시한다. 경로 선택 알고리즘은 바꾸지 않는다.

**Architecture:** 기존 `SAMPLE_STEP_M`(5 m) 샘플을 **경로 좌표열 전체**에 한 번 적용해 SUN/SHADE 런을 센다(엣지 경계에서 끊기지 않음). 급수는 런타임 Overpass를 쓰지 않고, 전처리 GeoJSON을 메모리에 올린 뒤 경로 LineString과의 평면 최단거리로 필터한다. 급수는 `PathDto.water_spots`로 `/routes`에 additive 추가하고, 지도는 `state.selected` 경로의 점만 그린다.

**Tech Stack:** 기존과 동일 (Python 3.12, FastAPI, Shapely, pytest, React, MapLibre, Vitest). 새 라이브러리 없음.

**Spec:** `FeatureAddition.md` (제품 요구). 아래 Global Constraints가 코드와의 정합을 위해 스펙 문장을 고정한 부분이다.

## Global Constraints

- 라우팅 가중치·다익스트라·`α = 3`을 바꾸지 않는다. 급수를 waypoint/보너스로 쓰지 않는다.
- 보행 속도는 `WALK_M_PER_MIN = 80.0`만 쓴다. 초 = `round(m / 80 * 60)`. 새 속도 상수를 만들지 않는다.
- `duration_min`은 유지한다. 스펙 예시의 `duration_seconds`는 PathDto에 넣지 않는다.
- `max_continuous_sun_*`는 additive. 기존 필드 이름·타입을 바꾸지 않는다.
- 야간(`shadows is None`): `max_continuous_sun_m = 0`, `max_continuous_sun_seconds = 0`. 주간에 그림자가 비면 전 구간 SUN으로 본다.
- 샘플링은 `ShadowIndex`의 5 m 근사를 그대로 쓴다. 정확한 line∩polygon 교차는 추가하지 않는다.
- 급수 검색은 **런타임 OSM/Overpass/Nominatim 호출 금지**. 전처리 파일만 읽는다.
- `WATER_BUFFER_M = 50`. 거리는 경로 polyline ↔ 점의 평면(EPSG:6677) 최단거리, 정수 m.
- `source`는 이번 구현에서 `"OSM"`만. TOKYO_WATER 처리 코드는 만들지 않는다.
- UI 문구는 일본어. 이름이 없는 스팟에 OSM 이름을 지어내지 않는다. 카드 폴백 라벨은 `copy.waterSpot`만 쓴다.
- 기존 테스트는 유지하고, 새 필드 때문에 깨지면 픽스처에 기본값만 보탠다.

## File Structure

```
api/src/hikage_navi/
  constants.py          # WATER_BUFFER_M 추가
  exposure.py           # SUN 런렝스 + 초 환산 (신규)
  shadows.py            # 경로 샘플 마스크 (기존 shade_lengths와 동일 근사)
  routing.py            # PathResult에 max_continuous_sun_*
  water.py              # WaterSpot 로드·경로 주변 검색 (신규)
  schemas.py            # PathDto 필드 additive
  app.py                # DTO 매핑 + water 로드
api/scripts/preprocess.py
api/tests/
  test_exposure.py      # 런렝스 Case 1–6
  test_water.py         # 50 m 필터
  test_routing.py       # PathResult 필드
  test_app.py           # /routes 응답
web/src/
  types.ts / api.ts / copy.ts / state.ts
  Panel.tsx / MapView.tsx / App.tsx / styles.css
data/fixtures/shibuya-water-spots.geojson
data/processed/shibuya-water-spots.geojson   # 전처리 후 git 추적
```

---

### Task 1: 연속 직사광선 런렝스

**Files:**
- Create: `api/src/hikage_navi/exposure.py`
- Create: `api/tests/test_exposure.py`
- Modify: `api/src/hikage_navi/shadows.py` (`sample_shade`, `max_continuous_sun_m`)

**Interfaces:**
- Consumes: `hikage_navi.constants.WALK_M_PER_MIN`, `hikage_navi.shadows.SAMPLE_STEP_M`, `ShadowIndex`
- Produces:
  - `max_run_sun_m(shaded: Sequence[bool], steps: Sequence[float]) -> float`
  - `sun_seconds(distance_m: float) -> int`
  - `ShadowIndex.sample_shade(coords) -> tuple[np.ndarray, np.ndarray]`  # (steps_m, shaded)
  - `ShadowIndex.max_continuous_sun_m(coords) -> float`

- [ ] **Step 1: Write the failing test**

`api/tests/test_exposure.py`:

```python
import pytest

from hikage_navi.constants import WALK_M_PER_MIN
from hikage_navi.exposure import max_run_sun_m, sun_seconds
from hikage_navi.shadows import SAMPLE_STEP_M, ShadowIndex
from shapely.geometry import box, LineString


def test_all_shade_is_zero():
    assert max_run_sun_m([True, True, True], [5.0, 5.0, 5.0]) == 0.0


def test_all_sun_is_full_length():
    assert max_run_sun_m([False, False, False], [5.0, 5.0, 5.0]) == 15.0


def test_first_sun_run_wins():
    # SUN SUN SHADE SUN
    assert max_run_sun_m([False, False, True, False], [5, 5, 5, 5]) == 10.0


def test_second_sun_run_wins():
    # SUN SHADE SUN SUN SUN
    assert max_run_sun_m([False, True, False, False, False], [5, 5, 5, 5, 5]) == 15.0


def test_shade_resets_between_suns():
    # SUN SHADE SUN SHADE SUN
    assert max_run_sun_m([False, True, False, True, False], [5, 5, 5, 5, 5]) == 5.0


def test_sun_seconds_reuses_walk_speed():
    assert sun_seconds(24.0) == int(round(24.0 / WALK_M_PER_MIN * 60))
    assert sun_seconds(24.0) == 18


def test_index_max_sun_crosses_edge_boundary():
    """한 폴리라인 = Edge A+B. 양 끝만 그늘이면 가운데 SUN이 한 런."""
    coords = [(139.7016, 35.6580), (139.7027, 35.6580)]
    line = LineString(coords)
    # 선의 양 끝 ~1/6만 덮는 상자 두 개 → 가운데는 SUN
    xs = [c[0] for c in coords]
    minx, maxx = min(xs), max(xs)
    span = maxx - minx
    left = box(minx - 0.001, 35.6575, minx + span / 6, 35.6585)
    right = box(maxx - span / 6, 35.6575, maxx + 0.001, 35.6585)
    index = ShadowIndex.from_geometry(left.union(right))
    # 샘플 6개라면 SHADE SUN SUN SUN SUN SHADE → 연속 SUN 4 * ~5 m
    got = index.max_continuous_sun_m(coords)
    assert got == pytest.approx(4 * SAMPLE_STEP_M, abs=SAMPLE_STEP_M)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_exposure.py -v`

Expected: FAIL (`ModuleNotFoundError: hikage_navi.exposure` 또는 `max_run_sun_m` / `max_continuous_sun_m` 없음)

- [ ] **Step 3: Write minimal implementation**

`api/src/hikage_navi/exposure.py`:

```python
from collections.abc import Sequence

from hikage_navi.constants import WALK_M_PER_MIN


def max_run_sun_m(shaded: Sequence[bool], steps: Sequence[float]) -> float:
    best = 0.0
    cur = 0.0
    for is_shade, step in zip(shaded, steps):
        if is_shade:
            cur = 0.0
        else:
            cur += float(step)
            if cur > best:
                best = cur
    return best


def sun_seconds(distance_m: float) -> int:
    return int(round(float(distance_m) / WALK_M_PER_MIN * 60.0))
```

`shadows.py`의 `ShadowIndex`에, `shade_lengths`와 **같은** 보간(중점, `SAMPLE_STEP_M`, `MAX_SAMPLES`)으로 한 선의 `(steps, shaded)`를 돌려주는 `sample_shade`를 추가한다. 트리가 비면 `shaded`는 전부 False(SUN). `max_continuous_sun_m`는 `sample_shade` → `max_run_sun_m`.

`shade_lengths` 로직을 복사하지 말고, 샘플 생성을 헬퍼로 뽑아 둘 다 쓰게 리팩터해도 된다. 결과(그늘 길이)가 기존 테스트와 같아야 한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_exposure.py tests/test_shadows.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/hikage_navi/exposure.py api/src/hikage_navi/shadows.py api/tests/test_exposure.py
git commit -m "$(cat <<'EOF'
feat: 경로 샘플로 최대 연속 직사광선 길이를 계산한다

EOF
)"
```

---

### Task 2: PathResult·API에 지표 추가

**Files:**
- Modify: `api/src/hikage_navi/routing.py`
- Modify: `api/src/hikage_navi/schemas.py`
- Modify: `api/src/hikage_navi/app.py` (`_path_dto`)
- Modify: `api/tests/test_routing.py`
- Modify: `api/tests/test_app.py`

**Interfaces:**
- Consumes: `ShadowIndex.max_continuous_sun_m`, `sun_seconds`
- Produces: `PathResult.max_continuous_sun_m: int`, `PathResult.max_continuous_sun_seconds: int` (정수 m·초, 반올림). `PathDto` 동명 필드. 야간/그림자 없음(`index is None`)이면 둘 다 `0`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_routing.py`에 추가:

```python
def test_shortest_without_shadows_has_zero_continuous_sun():
    g = load_walk_graph(FIXTURE)
    result = shortest_path(g, 1, 3)
    assert result.max_continuous_sun_m == 0
    assert result.max_continuous_sun_seconds == 0


def test_shortest_with_shadows_reports_continuous_sun():
    g = load_walk_graph(FIXTURE)
    shadow = box(139.7010, 35.6575, 139.7030, 35.6590)
    result = shortest_path(g, 1, 3, shadows=shadow)
    assert result.max_continuous_sun_m >= 0
    assert result.max_continuous_sun_seconds == int(
        round(result.max_continuous_sun_m / 80.0 * 60)
    )
```

`api/tests/test_app.py`에 추가:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_routing.py::test_shortest_without_shadows_has_zero_continuous_sun tests/test_app.py::test_routes_include_max_continuous_sun_fields -v`

Expected: FAIL (`AttributeError` 또는 응답에 키 없음)

- [ ] **Step 3: Write minimal implementation**

`PathResult`에 두 필드를 추가한다. `_metrics` 시그니처에 `index: ShadowIndex | None`를 넘긴다.

- `index is None` → `max_m = 0`
- 그 외 → `max_m = index.max_continuous_sun_m(coords)` (이미 만든 경로 좌표열, 이동 순서)

```python
from hikage_navi.exposure import sun_seconds

max_continuous_sun_m = int(round(max_m))
max_continuous_sun_seconds = sun_seconds(max_continuous_sun_m)
```

`shortest_path(..., shadows=None)`는 지금처럼 그늘 맵 없이 `_metrics`를 호출하므로 연속 태양은 0이다. `path_metrics` / 그림자가 있는 `shortest_path` / `shadiest_path`만 값을 채운다.

`schemas.PathDto`와 `app._path_dto`에 같은 두 필드를 넣는다.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_routing.py tests/test_app.py tests/test_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/hikage_navi/routing.py api/src/hikage_navi/schemas.py api/src/hikage_navi/app.py api/tests/test_routing.py api/tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: 경로 API에 최대 연속 직사광선 지표를 넣는다

EOF
)"
```

---

### Task 3: 경로 카드에 연속 직사광선 표시

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/api.test.ts`
- Modify: `web/src/copy.ts`
- Modify: `web/src/Panel.tsx`

**Interfaces:**
- Consumes: `PathDto.max_continuous_sun_seconds`
- Produces:
  - `formatContinuousSun(p: PathDto) -> string` — `連続直射日光 最大18秒`. 60초 이상이면 `最大2分` 또는 `最大2分15秒` (0초 분 단위는 생략).
  - 야간 S4에서는 이 문구를 그리지 않는다.

- [ ] **Step 1: Write the failing test**

`web/src/api.test.ts` — 기존 `PathDto` 픽스처에 `max_continuous_sun_m`, `max_continuous_sun_seconds`, `water_spots: []`를 넣고, 아래를 추가한다.

```typescript
import { formatContinuousSun, formatPath } from "./api";

function samplePath(over: Partial<PathDto> = {}): PathDto {
  return {
    coordinates: [],
    distance_m: 1200,
    duration_min: 15,
    shade_m: 240,
    sun_m: 960,
    shade_pct: 20,
    max_continuous_sun_m: 24,
    max_continuous_sun_seconds: 18,
    water_spots: [],
    ...over,
  };
}

it("formatContinuousSun shows max seconds", () => {
  expect(formatContinuousSun(samplePath())).toBe("連続直射日光 最大18秒");
});

it("formatContinuousSun uses minutes when >= 60 seconds", () => {
  expect(
    formatContinuousSun(samplePath({ max_continuous_sun_seconds: 135 })),
  ).toBe("連続直射日光 最大2分15秒");
});

it("formatContinuousSun omits leftover seconds at whole minutes", () => {
  expect(
    formatContinuousSun(samplePath({ max_continuous_sun_seconds: 120 })),
  ).toBe("連続直射日光 最大2分");
});
```

기존 `formatPath` 테스트는 거리·분·그늘% 문자열이 **그대로**인지 확인한다 (연속 태양은 다음 줄).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/api.test.ts`

Expected: FAIL (`formatContinuousSun` 없음 또는 PathDto 타입 오류)

- [ ] **Step 3: Write minimal implementation**

`types.ts`의 `PathDto`:

```typescript
max_continuous_sun_m: number;
max_continuous_sun_seconds: number;
water_spots: WaterSpotDto[];
```

`WaterSpotDto`는 Task 5에서 본체를 채운다. 지금은

```typescript
export type WaterSpotDto = {
  id: string;
  name: string | null;
  lat: number;
  lon: number;
  type: string;
  source: string;
  bottle_refill: boolean | null;
  access: string | null;
  opening_hours: string | null;
  route_distance_m: number;
};
```

를 미리 두어도 된다 (프론트만, 아직 API에 없어도 `[]`).

`copy.ts`:

```typescript
continuousSun: (label: string) => `連続直射日光 最大${label}`,
```

`api.ts`:

```typescript
export function formatContinuousSun(p: PathDto): string {
  const s = p.max_continuous_sun_seconds;
  const min = Math.floor(s / 60);
  const sec = s % 60;
  const label =
    min === 0 ? `${sec}秒` : sec === 0 ? `${min}分` : `${min}分${sec}秒`;
  return `連続直射日光 最大${label}`;
}
```

`Panel.tsx` S3 경로 카드: `formatPath` 아래에 `<span className="muted">{formatContinuousSun(...)}</span>`. same_route 한 줄 표시에도 최단 경로의 연속 태양을 붙인다. S4(야간)에는 넣지 않는다.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/types.ts web/src/api.ts web/src/api.test.ts web/src/copy.ts web/src/Panel.tsx
git commit -m "$(cat <<'EOF'
feat: 경로 카드에 최대 연속 직사광선 시간을 보여 준다

EOF
)"
```

---

### Task 4: 경로 주변 급수 검색 (순수 함수)

**Files:**
- Create: `api/src/hikage_navi/water.py`
- Create: `api/tests/test_water.py`
- Modify: `api/src/hikage_navi/constants.py` (`WATER_BUFFER_M = 50.0`)
- Create: `data/fixtures/shibuya-water-spots.geojson`

**Interfaces:**
- Consumes: `geo.to_planar`, Shapely `LineString.distance(Point)`
- Produces:
  - `@dataclass WaterSpot` — `id, name, lat, lon, type, source, bottle_refill, access, opening_hours`
  - `load_water_spots(path: Path) -> list[WaterSpot]` — 파일 없으면 `[]`
  - `nearby_water_spots(spots, route_coords, buffer_m=WATER_BUFFER_M) -> list[WaterSpotMatch]`
  - `WaterSpotMatch` = `WaterSpot` + `route_distance_m: int`
  - `type`은 OSM `amenity=drinking_water` 또는 `drinking_water=yes` → `"DRINKING_WATER"`. `bottle=yes`이면 type `"BOTTLE_REFILL"`이어도 되고, 아니면 `bottle_refill=True`만 켜도 된다. 한 규칙을 코드와 테스트에 같이 박는다: **`bottle=yes` → `bottle_refill=True`, type은 `DRINKING_WATER` 유지.**

픽스처 경로(노드 1–3 근처):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "osm-near",
        "name": null,
        "type": "DRINKING_WATER",
        "source": "OSM",
        "bottle": null,
        "access": null,
        "opening_hours": null
      },
      "geometry": { "type": "Point", "coordinates": [139.70160, 35.65800] }
    },
    {
      "type": "Feature",
      "properties": {
        "id": "osm-far",
        "name": "遠い水",
        "type": "DRINKING_WATER",
        "source": "OSM",
        "bottle": "yes",
        "access": "yes",
        "opening_hours": "09:00-18:00"
      },
      "geometry": { "type": "Point", "coordinates": [139.71000, 35.66500] }
    }
  ]
}
```

`osm-near`는 픽스처 경로(노드 2) 위 → 포함. `osm-far`는 시부야 안이지만 경로에서 수백 m → 제외.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from hikage_navi.constants import WATER_BUFFER_M
from hikage_navi.graph import load_walk_graph
from hikage_navi.routing import shortest_path
from hikage_navi.water import load_water_spots, nearby_water_spots

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data/fixtures"
ROUTE = [(139.70050, 35.65900), (139.70160, 35.65800), (139.70270, 35.65700)]


def test_buffer_constant_is_50():
    assert WATER_BUFFER_M == 50.0


def test_includes_spot_within_buffer():
    spots = load_water_spots(FIXTURE_DIR / "shibuya-water-spots.geojson")
    found = nearby_water_spots(spots, ROUTE)
    ids = {s.id for s in found}
    assert "osm-near" in ids
    near = next(s for s in found if s.id == "osm-near")
    assert near.route_distance_m <= 50


def test_excludes_spot_beyond_buffer():
    spots = load_water_spots(FIXTURE_DIR / "shibuya-water-spots.geojson")
    ids = {s.id for s in nearby_water_spots(spots, ROUTE)}
    assert "osm-far" not in ids


def test_empty_spots_returns_empty():
    assert nearby_water_spots([], ROUTE) == []


def test_missing_file_loads_empty(tmp_path):
    assert load_water_spots(tmp_path / "none.geojson") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_water.py -v`

Expected: FAIL (모듈/상수 없음)

- [ ] **Step 3: Write minimal implementation**

`constants.py`: `WATER_BUFFER_M = 50.0`

`water.py` 개요:

- GeoJSON Point만 읽는다. `id` 없으면 `f"{lon:.5f},{lat:.5f}"`.
- `name`이 빈 문자열이면 `None`.
- 평면 변환 후 `LineString(route_xy).distance(Point(spot_xy))`.
- `distance <= buffer_m`만 남기고 `route_distance_m = int(round(distance))`.
- 거리 오름차순 정렬.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_water.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/hikage_navi/water.py api/src/hikage_navi/constants.py api/tests/test_water.py data/fixtures/shibuya-water-spots.geojson
git commit -m "$(cat <<'EOF'
feat: 경로 50m 안의 급수 스팟만 고른다

EOF
)"
```

---

### Task 5: `/routes`에 water_spots 부착

**Files:**
- Modify: `api/src/hikage_navi/schemas.py`
- Modify: `api/src/hikage_navi/app.py`
- Modify: `api/tests/test_app.py`

**Interfaces:**
- Consumes: `load_water_spots`, `nearby_water_spots`, 각 경로 `coords`
- Produces: `PathDto.water_spots: list[WaterSpotDto]`. 라우팅 가중치·노드 선택은 그대로. 파일 없으면 빈 배열.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_app.py::test_routes_water_spots_only_near_path -v`

Expected: FAIL (키 없음)

- [ ] **Step 3: Write minimal implementation**

`WaterSpotDto` (Pydantic) 필드는 프론트 `WaterSpotDto`와 동일. `PathDto.water_spots: list[WaterSpotDto] = []`.

`load_ctx`에서 `data_dir() / "shibuya-water-spots.geojson"`를 읽는다.

`_path_dto(p, spots)`가 `nearby_water_spots(all_spots, p.coords)` 결과를 넣는다. `shortest`와 `shadiest`는 **각자** 자기 좌표로 필터한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/ -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/hikage_navi/schemas.py api/src/hikage_navi/app.py api/tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: 경로 응답에 주변 급수 스팟을 붙인다

EOF
)"
```

---

### Task 6: 지도 마커·ON/OFF·선택 경로 연동

**Files:**
- Modify: `web/src/state.ts`, `web/src/state.test.ts`
- Modify: `web/src/types.ts` (`waterVisible`, `TOGGLE_WATER`)
- Modify: `web/src/MapView.tsx`
- Modify: `web/src/copy.ts`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.tsx` (필요 시 토글을 MapView/Panel 중 한곳에만)

**Interfaces:**
- Consumes: `state.selected`에 해당하는 `PathDto.water_spots`, `state.waterVisible`
- Produces: 선택 경로의 급수만 마커. OFF면 마커 제거. 경로 카드 클릭 시 마커 교체. 라우팅 재요청 없음.

기본값: `waterVisible: true` (경로가 있을 때 차별점이 보이게). RESET 시 `true`로 돌아간다.

- [ ] **Step 1: Write the failing test**

`web/src/state.test.ts`에 선택·토글 테스트를 추가한다. 파일이 얇으면 같은 패턴으로:

```typescript
it("TOGGLE_WATER flips waterVisible without clearing the route", () => {
  const withRoute = reduce(initialState(), {
    type: "ROUTE_OK",
    route: nightlessRoute(),
  });
  const off = reduce(withRoute, { type: "TOGGLE_WATER" });
  expect(off.waterVisible).toBe(false);
  expect(off.route).toBe(withRoute.route);
  expect(reduce(off, { type: "TOGGLE_WATER" }).waterVisible).toBe(true);
});
```

`nightlessRoute()`는 기존 테스트 픽스처가 있으면 재사용. 없으면 `shortest`/`shadiest`에 Task 3 PathDto 기본값을 넣는다.

팝업 문구 헬퍼를 `web/src/api.ts`에 두고 테스트한다:

```typescript
export function waterPopupLines(spot: WaterSpotDto): string[] {
  const lines: string[] = [];
  if (spot.name) lines.push(spot.name);
  else lines.push("給水スポット");
  lines.push("💧 給水可能");
  lines.push(`ルートから約${spot.route_distance_m}m`);
  if (spot.bottle_refill) lines.push("マイボトル給水可能");
  if (spot.opening_hours) lines.push(`利用時間 ${spot.opening_hours}`);
  return lines;
}
```

이름이 없을 때 `"給水スポット"`은 **카피**이지 OSM name 날조가 아니다. `opening_hours` 없으면 이용시간 줄을 만들지 않는다. `access`는 값이 있을 때만 한 줄.

`api.test.ts`:

```typescript
it("waterPopupLines omits missing optional fields", () => {
  const lines = waterPopupLines({
    id: "osm-near",
    name: null,
    lat: 35.658,
    lon: 139.7016,
    type: "DRINKING_WATER",
    source: "OSM",
    bottle_refill: null,
    access: null,
    opening_hours: null,
    route_distance_m: 28,
  });
  expect(lines).toEqual([
    "給水スポット",
    "💧 給水可能",
    "ルートから約28m",
  ]);
  expect(lines.join("\n")).not.toContain("利用時間");
  expect(lines.join("\n")).not.toContain("マイボトル");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test`

Expected: FAIL (`TOGGLE_WATER` / `waterPopupLines` 없음)

- [ ] **Step 3: Write minimal implementation**

상태: `waterVisible: boolean` (initial `true`). `TOGGLE_WATER`는 불리언만 뒤집는다. `SELECT`는 `selected`만 바꾼다.

`MapView`:
- `const path = state.selected === "shadiest" && state.route?.shadiest ? state.route.shadiest : state.route?.shortest`
- `spots = state.waterVisible && path ? path.water_spots : []`
- 기존 급수 마커를 지우고 `spots`로 다시 만든다. 루트 `div` + 안쪽 `.water-pin` (💧). MapLibre `Popup`에 `waterPopupLines`를 `<br>`로 잇는다.
- 출발/도착 핀 패턴(루트와 라벨 분리)을 재사용한다.

범례 또는 패널에 체크박스:

```text
💧 給水スポット
```

`copy.waterToggle = "給水スポット"`. 체크 해제 시 마커가 없어지는지 브라우저에서 한 번 확인한다 (Step 4 후 수동).

CSS: `.water-pin`은 `.pin`과 같되 배경을 `#0369a1` 정도로. `pointer-events: auto` (팝업용). 범례 토글은 44px 터치 영역.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test`

Expected: PASS

수동: 픽스처 API로 경로 검색 → 💧 표시 → 최단/그늘 카드 전환 시 마커 좌표가 바뀜 → 토글 OFF 시 제거.

- [ ] **Step 5: Commit**

```bash
git add web/src/state.ts web/src/state.test.ts web/src/types.ts web/src/MapView.tsx web/src/api.ts web/src/api.test.ts web/src/copy.ts web/src/styles.css web/src/Panel.tsx web/src/App.tsx
git commit -m "$(cat <<'EOF'
feat: 선택한 경로 주변 급수를 지도에서 켜고 끈다

EOF
)"
```

---

### Task 7: OSM 전처리로 시부야 급수 GeoJSON

**Files:**
- Modify: `api/scripts/preprocess.py`
- Modify: `.gitignore` (`!data/processed/shibuya-water-spots.geojson`)
- Modify: `web/src/copy.ts` attribution (급수가 OSM임을 한 단어로)
- Modify: `Dockerfile.api`는 `COPY data/processed` 이미 있으므로 파일만 생기면 이미지에 포함된다

**Interfaces:**
- Consumes: 기존 경계 폴리곤, `HIKAGE_USE_PBF` / osmnx 분기
- Produces: `data/processed/shibuya-water-spots.geojson`  
  태그: `amenity=drinking_water` **또는** `drinking_water=yes`. 경계와 교차하는 Point만. 런타임 네트워크 호출 없음.

- [ ] **Step 1: 추출 함수 스케폴딩 + 단위 테스트**

전처리 스크립트에 대한 pytest가 아직 없으면, `api/tests/test_water.py`에 **태그 → 내부 프로퍼티** 매핑만 테스트한다 (`water.py`의 `spot_from_osm_tags` 또는 preprocess와 공유하는 순수 함수).

```python
from hikage_navi.water import spot_from_properties

def test_maps_osm_tags_without_inventing_name():
    spot = spot_from_properties(
        {
            "id": "n1",
            "name": None,
            "amenity": "drinking_water",
            "bottle": "yes",
            "access": "yes",
            "opening_hours": "09:00-18:00",
        },
        lon=139.7,
        lat=35.65,
    )
    assert spot.name is None
    assert spot.bottle_refill is True
    assert spot.source == "OSM"
    assert spot.type == "DRINKING_WATER"
```

`load_water_spots`가 이 매핑을 쓰게 맞춘다.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_water.py::test_maps_osm_tags_without_inventing_name -v`

Expected: FAIL (`spot_from_properties` 없음)

- [ ] **Step 3: preprocess에 `build_water_spots(boundary)` 추가**

`osmnx.features_from_polygon(boundary, tags={"amenity": "drinking_water", "drinking_water": "yes"})` (PBF 경로면 pyrosm POI 커스텀 필터). Geometry가 Point가 아니면 centroid를 쓰지 말고 **Point만** 남긴다 (폴리곤 급수대 centroid는 이번 범위 밖).

출력 Feature properties: `id, name, type, source, bottle, access, opening_hours`.

`main()` 순서: boundary → buildings → walk graph → **water spots**.

`.gitignore`에 `!data/processed/shibuya-water-spots.geojson` 추가.

로컬에서 전처리를 돌릴 수 있으면 시부야 산출물을 커밋한다. Overpass가 막히면 픽스처만으로 테스트는 통과하고, processed 파일은 빈 FeatureCollection이 아니라 **실제 추출분**이 올 때까지 Docker 이미지에는 픽스처를 복사하지 않는다. processed가 없을 때 `load_water_spots`는 `[]`이므로 API는 죽지 않는다.

attribution: `copy.attribution`에 급수가 OSM임을 이미 도로와 같이 © OSM이면 문구를 늘리지 않는다. 급수 전용 문장은 넣지 않아도 된다.

- [ ] **Step 4: Run tests**

Run:

```
cd api && pytest tests/ -v
cd web && npm test
```

Expected: PASS

가능하면 전처리 실행:

```
cd api && python scripts/preprocess.py
```

(건물·그래프가 이미 있으면 water 단계만 돌리는 플래그 `HIKAGE_WATER_ONLY=1`를 넣어도 된다. 넣으면 `build_water_spots`만 호출.)

- [ ] **Step 5: Commit**

```bash
git add api/scripts/preprocess.py api/src/hikage_navi/water.py api/tests/test_water.py .gitignore data/processed/shibuya-water-spots.geojson
git commit -m "$(cat <<'EOF'
feat: 시부야 OSM 급수 스팟을 전처리한다

EOF
)"
```

processed 파일이 아직 없으면 그 경로는 `git add`에서 뺀다.

---

## Spec coverage (self-review)

| FeatureAddition | Task |
| --- | --- |
| §1·2·13·15 연속 SUN, 엣지 경계, 샘플 근사 | 1, 2 |
| §3 API `max_continuous_sun_*` additive | 2 |
| §4 UI 연속 직사광선 | 3 |
| §5–8 WaterSpot, 50 m, polyline 거리 | 4, 5, 7 |
| §9–11 마커, 팝업, ON/OFF, 선택 경로 | 6 |
| §12·16 라우팅/경유/대피소/WBGT 안 함 | 전 태스크 비범위 |
| §14 급수 테스트 Case 1–6 | 4, 5, 6 |

의도적으로 안 넣은 것: 연속 태양을 cost에 넣기, 급수 경유 재탐색, Cooling Shelter, 기온 알림, 도쿄 23구·모바일(기존 Task 11–14).

## 기존 계획과의 관계

`docs/superpowers/plans/2026-08-14-hikage-navi-v0.1.md` Task 11–14(모바일, 23구)와 **독립**이다. 차별화 기능을 먼저 넣는 것을 권장한다. Task 11을 나중에 할 때 경로 카드 두 줄·급수 토글이 좁은 화면에서도 보이도록 CSS만 이어서 조정하면 된다.
