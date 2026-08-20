# 시부야 / 東京23区 실데이터 전처리

사양: `docs/04-data-algorithm.md`  
산출물: `data/processed/` (gitignore — 대용량 geojson은 커밋하지 않음)

## 실행

```bash
cd api
. .venv/bin/activate
pip install -e ".[preprocess]"

# 기존: 시부야 단독 → data/processed/shibuya-*.{geojson,json}
python scripts/preprocess.py

# tokyo23: 구 코드 1개 (예: 시부야 13113)
python scripts/preprocess.py --wards 13113

# tokyo23: 여러 구 또는 전부
python scripts/preprocess.py --wards 13113,13104
python scripts/preprocess.py --wards all
```

### 시부야 단독 산출

| 파일 | 내용 |
| --- | --- |
| `shibuya-boundary.geojson` | 시부야구 Polygon |
| `shibuya-buildings.geojson` | PLATEAU LOD1, `properties.height` ≥ 2 |
| `shibuya-walk-graph.json` | OSM 보행 노드·엣지 |
| `shibuya-water-spots.geojson` | OSM 급수 (`amenity=drinking_water` 등) |

### tokyo23 산출 (`--wards`)

```
data/processed/tokyo23/
  boundary.geojson              # 선택 구 unary_union
  walk-graph.json               # union 폴리곤 보행망 1회
  wards/{code}/buildings.geojson
```

레이아웃 설명: `data/processed/tokyo23/README.md`

원본·캐시: `data/raw/` (CityGML zip, osmnx 캐시 등)

## 동작 요약

1. **경계** — 시부야: `osmnx.geocode_to_gdf("Shibuya, Tokyo, Japan")` 1회  
   tokyo23: 구별 Nominatim geocode → `unary_union`
2. **건물** — PLATEAU CityGML zip 다운로드 후 LOD 밑면·`measuredHeight` 파싱, 구 폴리곤 clip, height ≥ 2  
   tokyo23은 구 코드→URL 맵(`PLATEAU_CITYGML_URLS`) 사용. 미등록 코드는 명확히 실패.
3. **보행망** — 기본은 경계 폴리곤 Overpass → `osmnx.graph_from_polygon(..., network_type="walk")`  
   공개 OSRM/Nominatim **경로** API는 쓰지 않는다.
4. **급수** — 시부야 단독 모드만 OSM에서 추출. tokyo23 급수는 선택(미구현).

## CLI

| 인자 | 의미 |
| --- | --- |
| (없음) | 기존 시부야 단독 파이프라인 |
| `--wards 13113` | tokyo23 레이아웃, 해당 구만 |
| `--wards 13113,13101` | 여러 구 |
| `--wards all` | 東京23区 전부 (`13101`–`13123`) |

스모크(네트워크·시간 필요): `python scripts/preprocess.py --wards 13113`  
단위 테스트(다운로드 없음): `cd api && pytest tests/test_preprocess_tokyo23.py -v`

## 환경변수

| 변수 | 의미 |
| --- | --- |
| `HIKAGE_ROOT` | 저장소 루트 |
| `HIKAGE_CITYGML_URL` | 시부야 단독 모드 PLATEAU CityGML zip URL (기본: 2025 시부야) |
| `HIKAGE_USE_PBF=1` | Geofabrik `kanto-latest.osm.pbf` + `pyrosm` |
| `HIKAGE_WATER_ONLY=1` | 시부야 경계만 읽고 급수 스팟만 (tokyo23과 동시 사용 안 함) |

## API에 연결

```bash
export HIKAGE_DATA_DIR=/path/to/hikage-navi/data/processed
cd api && . .venv/bin/activate
uvicorn hikage_navi.app:app --port 8000
```

현재 런타임(`load_ctx`)은 시부야 단일 파일을 읽는다. tokyo23 레이아웃 연결은 Task 14(BuildingStore).

## 검증 메모 (로컬 실행 결과 예)

- 건물 ≈ 4만, 보행 노드 ≈ 1만 (기준: 각 1000 초과)
- 야간 `/routes`(하치코→에비스)는 수 초 내 응답
- 주간은 건물 그림자 합집합 비용이 커서 첫 요청이 길 수 있음 → 수용 전 `docs/04` 성능 목표(30분 버킷) 검토
