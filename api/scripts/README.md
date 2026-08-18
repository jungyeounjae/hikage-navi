# 시부야 실데이터 전처리

사양: `docs/04-data-algorithm.md`  
산출물: `data/processed/` (gitignore — 커밋하지 않음)

## 실행

```bash
cd api
. .venv/bin/activate
pip install -e ".[preprocess]"
python scripts/preprocess.py
```

생성 파일:

| 파일 | 내용 |
| --- | --- |
| `shibuya-boundary.geojson` | 시부야구 Polygon |
| `shibuya-buildings.geojson` | PLATEAU LOD1, `properties.height` ≥ 2 |
| `shibuya-walk-graph.json` | OSM 보행 노드·엣지 |
| `shibuya-water-spots.geojson` | OSM 급수 (`amenity=drinking_water` 등) |

원본·캐시: `data/raw/` (CityGML zip, osmnx 캐시 등)

## 동작 요약

1. **경계** — `osmnx.geocode_to_gdf("Shibuya, Tokyo, Japan")` 1회
2. **건물** — PLATEAU 渋谷区 CityGML zip 다운로드 후 LOD 밑면·`measuredHeight` 파싱
3. **보행망** — 기본은 시부야 폴리곤 Overpass → `osmnx.graph_from_polygon(..., network_type="walk")`  
   공개 OSRM/Nominatim **경로** API는 쓰지 않는다.
4. **급수** — 같은 OSM에서 `amenity=drinking_water` 등을 뽑아 GeoJSON으로 저장. 런타임 Overpass는 쓰지 않는다.

## 환경변수

| 변수 | 의미 |
| --- | --- |
| `HIKAGE_ROOT` | 저장소 루트 |
| `HIKAGE_CITYGML_URL` | PLATEAU CityGML zip URL (기본: 2025 시부야) |
| `HIKAGE_USE_PBF=1` | Geofabrik `kanto-latest.osm.pbf` + `pyrosm` |

## API에 연결

```bash
export HIKAGE_DATA_DIR=/path/to/hikage-navi/data/processed
cd api && . .venv/bin/activate
uvicorn hikage_navi.app:app --port 8000
```

`data/processed/shibuya-walk-graph.json`이 있으면 API가 fixtures 대신 processed를 우선한다.

## 검증 메모 (로컬 실행 결과 예)

- 건물 ≈ 4만, 보행 노드 ≈ 1만 (기준: 각 1000 초과)
- 야간 `/routes`(하치코→에비스)는 수 초 내 응답
- 주간은 건물 그림자 합집합 비용이 커서 첫 요청이 길 수 있음 → 수용 전 `docs/04` 성능 목표(30분 버킷) 검토
