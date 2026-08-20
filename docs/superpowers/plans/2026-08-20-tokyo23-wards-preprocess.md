# 東京23区 문안 + 전처리 (Task 12+13) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서비스 문안·상수를 東京23区로 바꾸고, 구별 PLATEAU·통합 OSM 보행망 전처리가 `data/processed/tokyo23/` 레이아웃을 만들 수 있게 한다.

**Architecture:** Task 12는 `wards.py` 상수와 UI/API outside 문안만 바꾼다. fixtures·런타임 `load_ctx`는 시부야 단일 파일을 유지한다. Task 13은 `preprocess.py`에 `--wards` 옵션과 tokyo23 출력 레이아웃을 추가한다. Task 14(런타임 BuildingStore)는 이 계획 밖이다.

**Tech Stack:** FastAPI/Python, React/TS copy, osmnx/geopandas/PLATEAU CityGML (기존 preprocess extras)

**Spec:** `docs/superpowers/plans/2026-08-14-hikage-navi-v0.1.md` Task 12–13; 승인된 통합 설계(채팅 2026-08-20)

## Global Constraints

- `MAX_STRAIGHT_M = 3000` 유지
- outside 확정 문안: `東京23区内の2点を指定してください`
- UI 일본어 키 유지, 값만 23区로
- 대용량 geojson은 git에 넣지 않음
- 기존 `shibuya-*` 산출·런타임 경로 호환 유지 (Task 14까지)
- 웹: `cd web && npm test` / API: `cd api && pytest tests/ -v`
- TDD: 실패 테스트 → 구현 → 통과 → 커밋

## Worktrees

| 역할 | path | branch |
| --- | --- | --- |
| Task 12 | `.worktrees/tokyo23-copy` | `feat/tokyo23-copy` |
| Task 13 | `.worktrees/tokyo23-preprocess` | `feat/tokyo23-preprocess` |
| 통합 | main repo → `feat/tokyo23-wards-preprocess`에 병합 | |

파일 소유(충돌 방지):
- **12만:** `wards.py`, `service.py`, `copy.ts`, `test_wards.py`, service/app 테스트 문안, docs 01/02, README 상태
- **13만:** `api/scripts/preprocess.py`, `api/scripts/README.md`, `data/processed/tokyo23/README.md`(또는 스크립트 주석)
- **공유:** `TOKYO_23_WARD_CODES` — 12가 `wards.py`에 둔다. 13은 `from hikage_navi.wards import TOKYO_23_WARD_CODES`만 사용. 13 브랜치에 wards가 없으면 **동일 내용의 wards.py를 최소 생성**하고, 병합 시 12 쪽을 채택한다.

---

### Task 12: 東京23区 문안·상수

**Files:**
- Create: `api/src/hikage_navi/wards.py`
- Create: `api/tests/test_wards.py`
- Modify: `api/src/hikage_navi/service.py`
- Modify: `api/tests/test_service.py` (outside 메시지 assert)
- Modify: `web/src/copy.ts`
- Modify: `docs/01-requirements.md`, `docs/02-functional-spec.md` (범위 한 줄)
- Modify: `README.md` / `README.ja.md` 상태(선택)

**Produces:**
- `TOKYO_23_WARD_CODES = [f"{c}" for c in range(13101, 13124)]`
- `OUTSIDE_MESSAGE = "東京23区内の2点を指定してください"`
- UI: `subtitle: "東京23区 · 徒歩"`, `s0sub` / `attribution` / `outsideHint` / `errors.outside` 동일 범위

- [x] Step 1: failing `test_wards.py`
- [x] Step 2: implement `wards.py` + wire service/copy
- [x] Step 3: pytest + npm test
- [x] Step 4: commit `feat: 서비스 범위를 東京23区 문안으로 넓힌다`

---

### Task 13: 東京23区 전처리

**Files:**
- Modify: `api/scripts/preprocess.py`
- Modify: `api/scripts/README.md`
- Create: `data/processed/tokyo23/README.md` (gitignore면 스크립트 docstring으로 대체 OK)

**Output layout:**
```
data/processed/tokyo23/
  boundary.geojson
  walk-graph.json
  wards/{code}/buildings.geojson
```

**Produces:**
- `--wards 13113` / `--wards all` CLI
- 구 코드→PLATEAU CityGML URL 맵 (없는 구는 명확히 fail)
- 구별 geocode → unary_union → boundary
- 구별 건물 clip → wards/{code}/buildings.geojson
- union 경계 walk-graph 1회
- 기존 shibuya 단독 경로 유지(기본 모드) 또는 `--tokyo23` 플래그로 새 레이아웃

- [ ] Step 1: scaffold WARDS/OUT paths + argparse
- [ ] Step 2: boundary union
- [ ] Step 3: per-ward buildings (reuse existing CityGML parser)
- [ ] Step 4: walk-graph from union
- [ ] Step 5: dry-run docs; do **not** commit large geojson
- [ ] Step 6: commit `feat: 東京23区용 구별 PLATEAU·OSM 전처리를 추가한다`

**Note:** 전체 23구 다운로드는 시간이 길다. 구현·커밋은 스크립트 완성까지. 실제 `--wards 13113` 스모크는 네트워크 가능 시 권장, 실패해도 URL 맵·CLI가 있으면 Task 통과로 본다(에이전트 환경 제약).

---

### Integration

- [ ] Merge `feat/tokyo23-copy` + `feat/tokyo23-preprocess` → `feat/tokyo23-wards-preprocess`
- [ ] Resolve `wards.py` if duplicated (prefer Task 12)
- [ ] Full `pytest` + `npm test`
- [ ] Do not push unless asked
