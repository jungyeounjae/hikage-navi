# data/processed/tokyo23

東京23区 전처리 산출물 루트. `python scripts/preprocess.py --wards …` 로 생성한다.

대용량 `*.geojson` / `walk-graph.json` 은 gitignore 대상이며 **커밋하지 않는다**. 이 README만 추적한다.

## 레이아웃

```
tokyo23/
  boundary.geojson                 # 선택 구 경계 unary_union (Feature)
  walk-graph.json                  # union 폴리곤에서 뽑은 OSM 보행 그래프
  wards/
    13101/buildings.geojson        # 구별 PLATEAU 건물 (height ≥ 2)
    13101/meta.json                # bounds, max_height_m (런타임 구 선택용)
    13113/buildings.geojson
    …
```

## 생성 예

```bash
cd api && . .venv/bin/activate && pip install -e ".[preprocess]"
python scripts/preprocess.py --wards 13113          # 시부야만
python scripts/preprocess.py --wards all            # 23구 (다운로드·시간 큼)
```

구 코드는 행정코드 `13101`–`13123`. 상세는 `api/scripts/README.md`.
