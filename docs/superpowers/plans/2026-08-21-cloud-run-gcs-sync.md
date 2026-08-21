# Cloud Run GCS tokyo23 sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cloud Run API가 기동 시 GCS `processed/tokyo23`을 sync하고(버전이 같으면 스킵), 이미지 bake 없이 23区 API를 서빙한다.

**Architecture:** `python -m hikage_navi.gcs_sync`가 uvicorn 전에 실행된다. GCS `walk-graph.json`의 generation과 로컬 `.gcs-sync-stamp`를 비교해 필요할 때만 prefix를 `/data/tokyo23`으로 다운로드한다. 기존 `BuildingStore` / `is_tokyo23_layout` 런타임은 그대로 쓴다.

**Tech Stack:** Python 3.11+, `google-cloud-storage`, FastAPI/uvicorn, Docker, Cloud Build, Cloud Run, pytest

**Spec:** `docs/superpowers/specs/2026-08-21-cloud-run-gcs-sync-design.md`

## Global Constraints

- sync 대상은 `gs://hikage-navi-data/processed/tokyo23`만 (`raw/` 금지)
- 버전 앵커는 GCS `walk-graph.json` **generation** + 로컬 `{HIKAGE_DATA_DIR}/.gcs-sync-stamp`
- `HIKAGE_GCS_SYNC=0`이면 sync no-op (로컬·테스트)
- sync 실패 시 process exit ≠ 0 (불완전 데이터로 앱 기동 금지)
- Dockerfile에서 `COPY data/processed` 제거
- Cloud Run: memory **2Gi**, request timeout **≥ 300s**, env로 GCS URI·DATA_DIR·SYNC=1
- 런타임 SA에 버킷 `hikage-navi-data` `roles/storage.objectViewer`
- Vercel 연결은 비범위
- 이 저장소의 구형 git(2.23)은 `git commit`에 `--trailer`가 붙으면 실패할 수 있음 → 커밋은 `/usr/bin/git commit -F /tmp/msg.txt` 사용

---

## File structure

| 파일 | 책임 |
| --- | --- |
| `api/src/hikage_navi/gcs_sync.py` | URI 파싱, stamp, skip/download, `__main__` |
| `api/tests/test_gcs_sync.py` | mock 기반 단위 테스트 |
| `api/pyproject.toml` | `google-cloud-storage` 런타임 의존성 |
| `Dockerfile.api` | bake 제거, sync→uvicorn entrypoint |
| `cloudbuild.yaml` | 메모리·timeout·env |
| `docs/07-gcp-cicd.md` | bake → GCS sync 문서 |
| `docs/08-gce-preprocess.md` | Cloud Run이 GCS processed를 읽음을 한 줄 링크 |

---

### Task 1: `gcs_sync` — env / URI / stamp / skip 판정

**Files:**
- Create: `api/src/hikage_navi/gcs_sync.py`
- Create: `api/tests/test_gcs_sync.py`

**Interfaces:**
- Consumes: stdlib `os`, `pathlib`; (이 태스크에서는 GCS 클라이언트 미사용)
- Produces:
  - `DEFAULT_GCS_URI: str = "gs://hikage-navi-data/processed/tokyo23"`
  - `STAMP_NAME: str = ".gcs-sync-stamp"`
  - `parse_gcs_uri(uri: str) -> tuple[str, str]` → `(bucket, prefix)` prefix는 trailing `/` 없음. 예: `("hikage-navi-data", "processed/tokyo23")`
  - `sync_enabled(environ: Mapping[str, str] | None = None) -> bool` — `HIKAGE_GCS_SYNC`가 `"0"`/`"false"`/`"no"`(대소문자 무시)이면 False, 그 외(미설정 포함) True
  - `stamp_path(data_dir: Path) -> Path`
  - `read_stamp(data_dir: Path) -> str | None`
  - `write_stamp(data_dir: Path, generation: str) -> None` — tmp 파일 후 `replace`로 원자적 기록
  - `local_ready(data_dir: Path) -> bool` — `walk-graph.json`과 `boundary.geojson` 둘 다 파일로 존재
  - `should_skip_sync(data_dir: Path, remote_generation: str) -> bool` — `local_ready`이고 `read_stamp == remote_generation`

- [ ] **Step 1: Write the failing tests**

```python
# api/tests/test_gcs_sync.py
from pathlib import Path

import pytest

from hikage_navi.gcs_sync import (
    local_ready,
    parse_gcs_uri,
    read_stamp,
    should_skip_sync,
    stamp_path,
    sync_enabled,
    write_stamp,
)


def test_parse_gcs_uri():
    assert parse_gcs_uri("gs://hikage-navi-data/processed/tokyo23") == (
        "hikage-navi-data",
        "processed/tokyo23",
    )
    assert parse_gcs_uri("gs://b/p/q/") == ("b", "p/q")


def test_parse_gcs_uri_rejects_bad():
    with pytest.raises(ValueError):
        parse_gcs_uri("https://example.com/x")
    with pytest.raises(ValueError):
        parse_gcs_uri("gs://bucket-only")


def test_sync_enabled_defaults_true(monkeypatch):
    monkeypatch.delenv("HIKAGE_GCS_SYNC", raising=False)
    assert sync_enabled() is True
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "0")
    assert sync_enabled() is False
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "false")
    assert sync_enabled() is False


def test_stamp_roundtrip(tmp_path: Path):
    write_stamp(tmp_path, "12345")
    assert stamp_path(tmp_path).name == ".gcs-sync-stamp"
    assert read_stamp(tmp_path) == "12345"


def test_should_skip_requires_ready_and_matching_stamp(tmp_path: Path):
    assert should_skip_sync(tmp_path, "9") is False
    (tmp_path / "walk-graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "boundary.geojson").write_text("{}", encoding="utf-8")
    assert local_ready(tmp_path) is True
    assert should_skip_sync(tmp_path, "9") is False
    write_stamp(tmp_path, "9")
    assert should_skip_sync(tmp_path, "9") is True
    assert should_skip_sync(tmp_path, "10") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && . .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"); pytest tests/test_gcs_sync.py -v`

Expected: FAIL (import error / module missing)

- [ ] **Step 3: Implement minimal `gcs_sync.py` helpers**

```python
# api/src/hikage_navi/gcs_sync.py
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DEFAULT_GCS_URI = "gs://hikage-navi-data/processed/tokyo23"
STAMP_NAME = ".gcs-sync-stamp"
DEFAULT_DATA_DIR = Path("/data/tokyo23")


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI, got {uri!r}")
    rest = uri[5:]
    bucket, _, prefix = rest.partition("/")
    if not bucket or not prefix:
        raise ValueError(f"expected gs://bucket/prefix, got {uri!r}")
    return bucket, prefix.strip("/")


def sync_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get("HIKAGE_GCS_SYNC", "1")).strip().lower()
    return raw not in {"0", "false", "no"}


def stamp_path(data_dir: Path) -> Path:
    return data_dir / STAMP_NAME


def read_stamp(data_dir: Path) -> str | None:
    path = stamp_path(data_dir)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def write_stamp(data_dir: Path, generation: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = stamp_path(data_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(generation).strip() + "\n", encoding="utf-8")
    tmp.replace(path)


def local_ready(data_dir: Path) -> bool:
    return (data_dir / "walk-graph.json").is_file() and (
        data_dir / "boundary.geojson"
    ).is_file()


def should_skip_sync(data_dir: Path, remote_generation: str) -> bool:
    return local_ready(data_dir) and read_stamp(data_dir) == str(remote_generation)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && . .venv/bin/activate && pytest tests/test_gcs_sync.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'feat: GCS sync stamp·URI 헬퍼를 추가한다' > /tmp/hikage-commit-msg.txt
/usr/bin/git add api/src/hikage_navi/gcs_sync.py api/tests/test_gcs_sync.py
/usr/bin/git commit -F /tmp/hikage-commit-msg.txt
```

---

### Task 2: `gcs_sync` — 다운로드 + `main` (mock GCS)

**Files:**
- Modify: `api/src/hikage_navi/gcs_sync.py`
- Modify: `api/tests/test_gcs_sync.py`
- Modify: `api/pyproject.toml` (runtime dep `google-cloud-storage>=2.14`)

**Interfaces:**
- Consumes: Task 1 helpers; `google.cloud.storage.Client` (테스트에서는 duck-typed mock)
- Produces:
  - `download_prefix(*, client, bucket_name: str, prefix: str, data_dir: Path) -> None`
  - `sync_processed(*, client=None, gcs_uri: str | None = None, data_dir: Path | None = None, environ: Mapping[str, str] | None = None) -> str` — `"disabled"` | `"skipped"` | `"synced"`
  - `main() -> None` — `sync_processed()` 호출, 예외 시 `SystemExit(1)`
  - `__main__` 가드에서 `main()`

**Mock 규칙:** blob은 `name`, `generation`(int 또는 str), `download_to_filename(path)` 속성/메서드. `bucket.blob(name).reload()` 또는 `bucket.get_blob`으로 walk-graph generation을 얻도록 구현을 고정한다.

구현 고정 API (테스트가 가정):

```python
def remote_walk_graph_generation(client, bucket_name: str, prefix: str) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"{prefix}/walk-graph.json")
    blob.reload()  # sets .generation
    if blob.generation is None:
        raise FileNotFoundError("walk-graph.json missing in GCS")
    return str(blob.generation)
```

- [ ] **Step 1: Write the failing tests**

`test_gcs_sync.py`에 추가:

```python
from unittest.mock import MagicMock

from hikage_navi.gcs_sync import download_prefix, sync_processed


def _blob(name: str, generation: int = 1):
    b = MagicMock()
    b.name = name
    b.generation = generation
    b.download_to_filename = MagicMock()
    return b


def test_sync_processed_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "0")
    client = MagicMock()
    assert sync_processed(client=client, data_dir=tmp_path) == "disabled"
    client.bucket.assert_not_called()


def test_sync_processed_skips_when_stamp_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "1")
    (tmp_path / "walk-graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "boundary.geojson").write_text("{}", encoding="utf-8")
    write_stamp(tmp_path, "42")

    walk = _blob("processed/tokyo23/walk-graph.json", generation=42)
    bucket = MagicMock()
    bucket.blob.return_value = walk
    client = MagicMock()
    client.bucket.return_value = bucket

    assert sync_processed(client=client, data_dir=tmp_path) == "skipped"
    walk.download_to_filename.assert_not_called()


def test_sync_processed_downloads_when_stamp_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HIKAGE_GCS_SYNC", "1")
    prefix = "processed/tokyo23"
    walk = _blob(f"{prefix}/walk-graph.json", generation=7)
    boundary = _blob(f"{prefix}/boundary.geojson", generation=1)
    ward = _blob(f"{prefix}/wards/13113/buildings.geojson", generation=1)

    def download_to_filename(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("x", encoding="utf-8")

    for b in (walk, boundary, ward):
        b.download_to_filename.side_effect = download_to_filename

    bucket = MagicMock()
    bucket.blob.return_value = walk
    bucket.list_blobs.return_value = [walk, boundary, ward]
    client = MagicMock()
    client.bucket.return_value = bucket

    assert sync_processed(client=client, data_dir=tmp_path) == "synced"
    assert read_stamp(tmp_path) == "7"
    assert (tmp_path / "walk-graph.json").is_file()
    assert (tmp_path / "wards/13113/buildings.geojson").is_file()
    bucket.list_blobs.assert_called_once_with(prefix=prefix + "/")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && . .venv/bin/activate && pytest tests/test_gcs_sync.py -v`

Expected: FAIL (`download_prefix` / `sync_processed` missing)

- [ ] **Step 3: Add dependency and implement download + `sync_processed` + `main`**

`api/pyproject.toml` dependencies에 `"google-cloud-storage>=2.14"` 추가 후 `pip install -e ".[dev]"`.

`gcs_sync.py`에 이어서:

```python
import logging
import sys

logger = logging.getLogger(__name__)


def remote_walk_graph_generation(client, bucket_name: str, prefix: str) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"{prefix}/walk-graph.json")
    blob.reload()
    if getattr(blob, "generation", None) is None:
        raise FileNotFoundError(f"gs://{bucket_name}/{prefix}/walk-graph.json missing")
    return str(blob.generation)


def download_prefix(*, client, bucket_name: str, prefix: str, data_dir: Path) -> None:
    bucket = client.bucket(bucket_name)
    list_prefix = prefix if prefix.endswith("/") else prefix + "/"
    data_dir.mkdir(parents=True, exist_ok=True)
    for blob in bucket.list_blobs(prefix=list_prefix):
        name = blob.name
        if name.endswith("/"):
            continue
        rel = name[len(list_prefix) :]
        if not rel:
            continue
        dest = data_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))


def sync_processed(
    *,
    client=None,
    gcs_uri: str | None = None,
    data_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = environ if environ is not None else os.environ
    if not sync_enabled(env):
        logger.info("gcs_sync disabled (HIKAGE_GCS_SYNC)")
        return "disabled"
    uri = gcs_uri or env.get("HIKAGE_GCS_PROCESSED_URI") or DEFAULT_GCS_URI
    dest = Path(data_dir or env.get("HIKAGE_DATA_DIR") or DEFAULT_DATA_DIR)
    bucket_name, prefix = parse_gcs_uri(uri)
    if client is None:
        from google.cloud import storage

        client = storage.Client()
    generation = remote_walk_graph_generation(client, bucket_name, prefix)
    if should_skip_sync(dest, generation):
        logger.info("gcs_sync skip generation=%s dir=%s", generation, dest)
        return "skipped"
    logger.info("gcs_sync download generation=%s uri=%s -> %s", generation, uri, dest)
    download_prefix(client=client, bucket_name=bucket_name, prefix=prefix, data_dir=dest)
    if not local_ready(dest):
        raise RuntimeError(f"sync incomplete: missing walk-graph/boundary under {dest}")
    write_stamp(dest, generation)
    return "synced"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = sync_processed()
        logger.info("gcs_sync done: %s", result)
    except Exception:
        logger.exception("gcs_sync failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && . .venv/bin/activate && pytest tests/test_gcs_sync.py tests/test_app.py -v`

Expected: PASS (앱 회귀 포함)

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'feat: 기동 시 GCS tokyo23 sync를 구현한다' > /tmp/hikage-commit-msg.txt
/usr/bin/git add api/src/hikage_navi/gcs_sync.py api/tests/test_gcs_sync.py api/pyproject.toml
/usr/bin/git commit -F /tmp/hikage-commit-msg.txt
```

---

### Task 3: Dockerfile — bake 제거 + sync entrypoint

**Files:**
- Modify: `Dockerfile.api`

**Interfaces:**
- Consumes: `hikage_navi.gcs_sync:main` (Task 2)
- Produces: 이미지에 `data/processed` 없음; 기동 시 sync 후 uvicorn

- [ ] **Step 1: Replace `Dockerfile.api` contents**

```dockerfile
# API image for Cloud Run. Build from repo root:
#   docker build -f Dockerfile.api -t hikage-navi-api .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*

COPY api/pyproject.toml ./api/
COPY api/src ./api/src
RUN pip install --no-cache-dir ./api

ENV HIKAGE_DATA_DIR=/data/tokyo23
ENV HIKAGE_GCS_PROCESSED_URI=gs://hikage-navi-data/processed/tokyo23
ENV HIKAGE_GCS_SYNC=1
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "python -m hikage_navi.gcs_sync && uvicorn hikage_navi.app:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Sanity-check Dockerfile has no bake**

Run: `rg -n "COPY data/processed|HIKAGE_DATA_DIR" Dockerfile.api`

Expected: `COPY data/processed` **없음**; `HIKAGE_DATA_DIR=/data/tokyo23` 있음

- [ ] **Step 3: Optional local image build (Docker 있는 환경)**

Run: `docker build -f Dockerfile.api -t hikage-navi-api:gcs-sync .`

Expected: 빌드 성공. (데이터 bake 단계 없음)

Docker가 없으면 이 스텝을 건너뛰고 Cloud Build에서 검증한다.

- [ ] **Step 4: Commit**

```bash
printf '%s\n' 'build: API 이미지에서 processed bake를 제거하고 GCS sync로 기동한다' > /tmp/hikage-commit-msg.txt
/usr/bin/git add Dockerfile.api
/usr/bin/git commit -F /tmp/hikage-commit-msg.txt
```

---

### Task 4: Cloud Build / Run 설정 + IAM + 문서

**Files:**
- Modify: `cloudbuild.yaml`
- Modify: `docs/07-gcp-cicd.md`
- Modify: `docs/08-gce-preprocess.md` (Cloud Run이 `processed/tokyo23`을 읽음을 한 단락)

**Interfaces:**
- Consumes: Task 3 이미지 env 기본값
- Produces: deploy args — memory 2Gi, timeout 300, env 3개; 문서가 bake 대신 sync를 설명

- [ ] **Step 1: Update `cloudbuild.yaml` deploy args**

`gcloud run deploy` args를 다음으로 교체 (기존 image/region/platform/allow-unauthenticated/cpu/min/max/port 유지):

```yaml
      - --memory=2Gi
      - --cpu=1
      - --min-instances=0
      - --max-instances=3
      - --port=8080
      - --timeout=300
      - --set-env-vars=HIKAGE_DATA_DIR=/data/tokyo23,HIKAGE_GCS_PROCESSED_URI=gs://hikage-navi-data/processed/tokyo23,HIKAGE_GCS_SYNC=1
```

`--memory=1Gi`와 `HIKAGE_DATA_DIR=/app/data/processed`는 삭제.

- [ ] **Step 2: Rewrite data section in `docs/07-gcp-cicd.md`**

섹션 3의 데이터 문단을 다음 취지로 교체 (표의 Cloud Run 메모리도 **2Gi**로):

- 전처리 산출물은 **이미지에 넣지 않는다**
- 기동 시 `hikage_navi.gcs_sync`가 `gs://hikage-navi-data/processed/tokyo23` → `/data/tokyo23`
- 런타임 SA에 `roles/storage.objectViewer` on `hikage-navi-data`
- env: `HIKAGE_DATA_DIR`, `HIKAGE_GCS_PROCESSED_URI`, `HIKAGE_GCS_SYNC`
- raw는 GCE+GCS ([08](08-gce-preprocess.md))

- [ ] **Step 3: Add Cloud Run consumer note to `docs/08-gce-preprocess.md`**

문서 상단 또는 「역할」 근처에 한 단락:

> Cloud Run API는 기동 시 GCS `processed/tokyo23`만 sync한다. 절차·환경 변수는 [07-gcp-cicd.md](07-gcp-cicd.md).

- [ ] **Step 4: Grant IAM (실환경, 한 번)**

프로젝트 `hikage-navi`, 버킷 `hikage-navi-data`. Cloud Run 기본 런타임 SA는 보통  
`PROJECT_NUMBER-compute@developer.gserviceaccount.com`.

```bash
PROJECT_ID=hikage-navi
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gsutil iam ch "serviceAccount:${SA}:objectViewer" gs://hikage-navi-data
# 또는:
# gcloud storage buckets add-iam-policy-binding gs://hikage-navi-data \
#   --member="serviceAccount:${SA}" --role=roles/storage.objectViewer
```

Expected: IAM 반영 성공. (이미 있으면 no-op에 가깝게 통과)

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'docs: Cloud Run GCS sync 배포 설정과 CI/CD 문서를 갱신한다' > /tmp/hikage-commit-msg.txt
/usr/bin/git add cloudbuild.yaml docs/07-gcp-cicd.md docs/08-gce-preprocess.md
/usr/bin/git commit -F /tmp/hikage-commit-msg.txt
```

---

### Task 5: Cloud Run 배포 + 수용 검증

**Files:**
- (코드 변경 없음 — 배포·검증만)

**Interfaces:**
- Consumes: Tasks 1–4가 머지된 `feat/cloud-run-gcs-sync` 워크트리 루트
- Produces: 동작하는 Cloud Run URL; `/health`, `/boundary` 성공

- [ ] **Step 1: Push branch (배포에 소스 제출)**

```bash
/usr/bin/git push -u origin HEAD
```

- [ ] **Step 2: Submit Cloud Build from worktree root**

```bash
cd "$(git rev-parse --show-toplevel)"
gcloud config set project hikage-navi
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

Expected: BUILD SUCCESS, Cloud Run `hikage-navi-api` 새 리비전

실패 시: 로그에서 `gcs_sync failed` / permission denied면 Task 4 IAM 재확인. OOM이면 `--memory=4Gi`로 cloudbuild만 고쳐 재배포.

- [ ] **Step 3: Resolve service URL and hit health/boundary**

```bash
URL=$(gcloud run services describe hikage-navi-api \
  --region=asia-northeast1 --format='value(status.url)')
curl -sfS "$URL/health"
curl -sfS "$URL/boundary" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('type'), len(json.dumps(d)))"
```

Expected:
- `/health` 200
- `/boundary` GeoJSON Feature(또는 FeatureCollection)이며 payload가 시부야 단독 fixture보다 큼(수십 KB 이상)

- [ ] **Step 4: Confirm bake absent and logs show sync**

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND textPayload:"gcs_sync"' \
  --project=hikage-navi --limit=20 --format='value(textPayload)'
```

Expected: `gcs_sync download` 또는 `gcs_sync skip` / `gcs_sync done` 로그. Dockerfile에 `COPY data/processed` 없음은 Task 3에서 이미 확인.

- [ ] **Step 5: Commit only if deploy required a config fix; otherwise note acceptance in PR body**

추가 커밋이 없으면 이 스텝은 스킵. 수정이 있으면 `/usr/bin/git commit` 후 재배포.

---

## Self-review (plan vs spec)

| Spec 요구 | Task |
| --- | --- |
| tokyo23만 sync / raw 제외 | Task 2 URI 기본값, Task 3–4 env |
| generation stamp skip | Task 1–2 |
| Python + google-cloud-storage | Task 2 |
| bake 제거 + entrypoint | Task 3 |
| Cloud Run 2Gi / timeout / env / IAM | Task 4 |
| docs 07/08 | Task 4 |
| 단위 테스트 mock | Task 1–2 |
| 실배포 /health /boundary | Task 5 |
| Vercel 비범위 | Task 없음 (의도) |

Placeholder / TBD: 없음.  
타입·이름: `sync_processed` → `"disabled"|"skipped"|"synced"` 전 태스크 일치.
