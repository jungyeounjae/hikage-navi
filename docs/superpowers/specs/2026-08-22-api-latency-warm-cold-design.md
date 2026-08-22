# Cloud Run API 지연 단축 (warm + cold, 상시 비용 없음) 설계

상태: 확정 (2026-08-22)  
관련: [2026-08-21-cloud-run-gcs-sync-design.md](./2026-08-21-cloud-run-gcs-sync-design.md), `origin/master` tokyo23 런타임

## 목표

상용 Cloud Run API에서 **`min-instances=1` 없이** warm·cold 지연을 줄여 브라우저 `Failed to fetch`를 없앤다.

알고리즘·샘플링·simplify는 바꾸지 않아 **배경 지도·경로 좌표열·그늘%·그림자 폴리곤이 최적화 전과 같다.**

## 확정된 결정

| 항목 | 선택 |
| --- | --- |
| 범위 | warm (`/routes`, `/shadows`) + cold (GCS sync + 그래프 로드) |
| 접근 | 같은 계산을 더 싸게 (공간 색인, 인접 리스트 Dijkstra, `length_m` 재사용, GCS 병렬 다운로드) |
| 상시 비용 | `min-instances=0` 유지. 요청 중 CPU만 사용 |
| 배포 자원 | 메모리 **4Gi**, CPU **2** (`cloudbuild.yaml`에 반영). CPU always-allocated 아님 |
| 성공 기준 A | warm `/routes` ≤ 8s, warm `/shadows` ≤ 5s, 콜드 첫 요청 ≤ 25s |

## 비범위

- `min-instances=1`
- `SAMPLE_STEP_M` / `RENDER_SIMPLIFY_M` / `DETOUR_MARGIN_M` / `ALPHA_SHADE` 변경
- walk-graph 바이너리 포맷·전처리 재실행
- 프론트 타임아웃 UX·로딩 카피
- Vercel 설정 변경

## 아키텍처

```
콜드 스타트
  GCS stamp 비교
    → 다를 때만 병렬 다운로드
    → walk-graph 로드 (length_m 있으면 haversine 생략)
    → 노드 격자 색인 + 인접 리스트 구축
    → uvicorn 수신

warm 요청
  /routes: 스냅(색인) → corridor subgraph → 최단
         → ShadowIndex(기존) → 그늘 경로(인접 리스트 Dijkstra)
  /shadows: 기존 bbox 선택 + union + 캐시 8칸
```

엔드포인트·응답 스키마·에러 코드·일본어 문안은 유지한다.

## 컴포넌트

### WalkGraph 로드

- JSON 간선에 `length_m`이 있으면 그대로 사용한다.
- 없으면 기존처럼 좌표 haversine으로 계산한다 (픽스처·구 포맷 호환).
- 노드 좌표·간선 `(u,v,coords)`는 변경하지 않는다.

### 스냅 (격자 색인)

- 기동 시 노드를 약 100 m 격자 칸에 넣는다.
- `snap_to_node`는 핀 주변 칸만 검색한다. 최종 판정은 `SNAP_MAX_M`(75 m) 그대로.
- 동률 시: 더 가까운 노드, 거리까지 같으면 더 작은 node id (결정적).

### 경로 탐색

- 기동 시 인접 리스트 `(이웃, Edge)`를 만든다.
- 최단·그늘 경로는 corridor subgraph 위에서 이 리스트로 Dijkstra를 돌린다.
- 요청마다 NetworkX 그래프를 새로 만들지 않는다.
- 가중치: 최단 = `length_m`, 그늘 = `d_shade + ALPHA_SHADE * d_sun` (기존과 동일).
- `subgraph_in_bbox` / `DETOUR_MARGIN_M=300` 유지.

### 그림자

- `ShadowIndex.from_buildings`, 5 m 샘플, union simplify 1 m, `/shadows` 캐시 크기 8 유지.
- `BuildingStore` 구 교차 + bbox 선택 유지.

### GCS sync

- generation stamp 비교·skip 로직 유지.
- `download_prefix`만 `ThreadPoolExecutor`로 blob 병렬 다운로드.
- 실패 시 프로세스 종료 (기존과 동일).

## 배포 · 관측

| 항목 | 값 |
| --- | --- |
| `cloudbuild.yaml` memory | **4Gi** (상용에 이미 수동 반영된 값과 맞춤) |
| `cloudbuild.yaml` cpu | **2** (요청 과금만, 인스턴스 상시 기동 아님) |
| min-instances | **0** |
| request timeout | 기존 ≥ 300s 유지 |
| 관측 | Cloud Logging에서 `gcs_sync` skip/download, `/routes`·`/shadows` latency (배포 후 curl `-w time_total`) |

구현 베이스는 `origin/master`의 tokyo23 + GCS sync 코드다. 모바일 전용 브랜치와 충돌하면 master에서 작업 브랜치를 딴다.

## 테스트

- `length_m` 유/무 JSON → 동일 그래프
- 스냅: 동일 핀 → 동일 노드, 75 m 밖 `SnapError`
- 최단·그늘: 동일 입력에서 기존과 같은 `node_ids` (픽스처)
- GCS: stamp 일치 → download 0회; 불일치 → 각 blob 1회 다운로드 (mock)
- 기존 `test_app` / `test_service` / `test_routing` / `test_gcs_sync` 회귀

## 수용 기준

- [ ] warm `POST /routes` ≤ 8 s (상용 Cloud Run)
- [ ] warm `GET /shadows` (뷰포트 bbox) ≤ 5 s
- [ ] 콜드 첫 요청(sync+로드 포함) ≤ 25 s, 브라우저 Failed to fetch 없음
- [ ] 픽스처에서 경로 `node_ids`·그늘%가 최적화 전과 동일
- [ ] `min-instances=0`, memory 4Gi·CPU 2가 `cloudbuild.yaml`에 있음

## 에러 처리

- outside / too_far / snap / disconnected 문안·HTTP 400 유지
- GCS sync 실패 → exit 1 (Cloud Run 재시도)
- 격자 후보가 비어도 최종은 `SNAP_MAX_M`으로 판정
