# Cloud Run 기동 시 GCS sync (tokyo23) 설계

상태: 확정 (2026-08-21)  
관련: [docs/07-gcp-cicd.md](../../07-gcp-cicd.md), [docs/08-gce-preprocess.md](../../08-gce-preprocess.md), tokyo23 `BuildingStore` 런타임

## 목표

상용 Cloud Run API가 **시부야 bake 이미지가 아니라** GCS의 `processed/tokyo23`을 읽어 東京23区 경계·그림자·경로를 제공한다.

기동 시 GCS에서 sync하고, **버전이 같으면 재다운로드하지 않는다.**

## 확정된 결정

| 항목 | 선택 |
| --- | --- |
| sync 대상 | `gs://hikage-navi-data/processed/tokyo23`만 (`raw/` 제외). 시부야는 ward `13113`으로 포함됨 |
| 버전 정책 | GCS `walk-graph.json`의 **generation**과 로컬 stamp 비교 후, 불일치·부재 시에만 sync |
| 구현 | Python 모듈 + `google-cloud-storage` (이미지에 Cloud SDK 미포함) |
| 성공 기준 | 코드·이미지·문서 + **Cloud Run 실배포**까지 (`/health`, `/boundary` 확인). Vercel 연결은 비범위 |

## 비범위

- Vercel 웹 연결·공개 URL CORS 최종 정리
- Cloud Storage FUSE / 마운트
- Cloud Run Job·전처리 자동화
- `raw/` sync, 시부야 `shibuya-*` bake 병행
- `min-instances=1`로 콜드 스타트 제거

## 아키텍처

```
GCS gs://hikage-navi-data/processed/tokyo23/
        │  기동 시 (generation 변경 시에만)
        ▼
Cloud Run 컨테이너
  /data/tokyo23/
  HIKAGE_DATA_DIR=/data/tokyo23
  entrypoint: gcs_sync → uvicorn
        │
        ▼
공개 API (/health, /boundary, /shadows, /routes)
```

기존 tokyo23 런타임(`is_tokyo23_layout`, `BuildingStore`, `walk-graph.json`)을 그대로 사용한다.

## 동기화 모듈

**경로:** `api/src/hikage_navi/gcs_sync.py`  
**진입:** Docker entrypoint가 uvicorn 전에 호출 (또는 `python -m hikage_navi.gcs_sync`).

### 환경 변수

| 변수 | 기본값 | 역할 |
| --- | --- | --- |
| `HIKAGE_GCS_PROCESSED_URI` | `gs://hikage-navi-data/processed/tokyo23` | GCS 소스 prefix |
| `HIKAGE_DATA_DIR` | `/data/tokyo23` | 로컬 대상 디렉터리 |
| `HIKAGE_GCS_SYNC` | `1` | `0`이면 sync 생략 (로컬·단위 테스트·기존 픽스처) |

### 알고리즘

1. `HIKAGE_GCS_SYNC=0`이면 no-op 후 성공 종료.
2. URI에서 bucket·prefix 파싱. blob `walk-graph.json`(prefix 상대)의 **generation** 조회.
3. 로컬 stamp 파일: `{HIKAGE_DATA_DIR}/.gcs-sync-stamp` (generation 문자열 한 줄).
4. stamp가 generation과 같고 `walk-graph.json`·`boundary.geojson`이 있으면 → 스킵(로그: skip).
5. 아니면 prefix 아래 객체를 로컬 상대 경로로 다운로드(덮어쓰기). README 등 작은 파일 포함. 완료 후 stamp를 새 generation으로 원자적 기록.
6. sync 중 실패 → **프로세스 exit ≠ 0**. 불완전 데이터로 uvicorn를 기동하지 않음.

참고: tokyo23 루트에 전역 `meta.json`은 없다. ward별 `wards/*/meta.json`만 있으므로 버전 앵커는 **`walk-graph.json` generation**으로 둔다.

### 의존성

- 런타임: `google-cloud-storage`를 `api/pyproject.toml` 기본 dependencies에 추가.
- ADC: Cloud Run 런타임 서비스 계정. 로컬 검증 시 `gcloud auth application-default login` 또는 기존 ADC.

## 이미지 · 배포

### Dockerfile.api

- `COPY data/processed ...` **제거**.
- entrypoint 예: `python -m hikage_navi.gcs_sync && uvicorn hikage_navi.app:app --host 0.0.0.0 --port ${PORT}`.
- `HIKAGE_DATA_DIR` 기본 `/data/tokyo23`. `/data`는 컨테이너 쓰기 가능 영역.

### cloudbuild.yaml / Cloud Run

| 항목 | 값 |
| --- | --- |
| memory | **4Gi** |
| cpu | **2** |
| env | `HIKAGE_DATA_DIR=/data/tokyo23`, `HIKAGE_GCS_PROCESSED_URI=gs://hikage-navi-data/processed/tokyo23`, `HIKAGE_GCS_SYNC=1` |
| request timeout | **≥ 300s** (콜드 스타트 + 첫 sync) |
| min-instances | 0 |
| 기존 flow | Cloud Build → Artifact Registry → Cloud Run 유지 |

### IAM

- Cloud Run 런타임 SA → 버킷 `hikage-navi-data`에 `roles/storage.objectViewer`.
- 배포용 Cloud Build SA는 기존과 동일(이미지 push·run deploy).

## 문서 갱신

- `docs/07-gcp-cicd.md`: 「전처리 데이터를 api 이미지에 넣는다 / GCS 버킷은 만들지 않는다」를 **기동 시 GCS sync**로 교체. 환경 변수·IAM·메모리 표를 반영.
- `docs/08-gce-preprocess.md` 또는 짧은 상호 링크: GCS가 Cloud Run의 데이터 소스임을 명시.

## 테스트

- **단위:** `gcs_sync` — stamp 일치 시 download 0회; 불일치·부재 시 blob list 기반 download 호출 (GCS 클라이언트 mock).
- **회귀:** 기존 앱·BuildingStore 테스트는 `HIKAGE_GCS_SYNC=0` (또는 env unset + 로컬 픽스처)으로 유지.
- **배포 수용 (수동):**
  - [ ] Cloud Run이 GCS tokyo23으로 기동
  - [ ] `GET /boundary`가 23구 union (시부야 단독 아님)
  - [ ] 동일 generation 재기동 시 sync skip (로그)
  - [ ] 이미지에 `data/processed` bake 없음

## 성공 정의

1. `feat` 브랜치에 sync·Dockerfile·cloudbuild·문서·테스트 반영.
2. `gcloud builds submit`(또는 동등)으로 Cloud Run 리비전 배포.
3. 공개(또는 인증된) Cloud Run URL에서 `/health`·`/boundary` 성공.

Vercel `VITE_API_BASE_URL` 연결은 후속 작업.
