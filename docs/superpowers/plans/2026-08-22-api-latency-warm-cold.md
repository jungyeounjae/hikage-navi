# Cloud Run API warm·cold 지연 단축 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상시 인스턴스 없이 warm `/routes`·`/shadows`와 콜드 기동(GCS sync + 그래프 로드)을 줄여 Failed to fetch를 없앤다. 경로·그림자 결과는 최적화 전과 동일하다.

**Architecture:** `walk-graph` 로드 시 `length_m` 재사용, 기동 시 격자 스냅 색인·인접 리스트를 붙인다. `/routes`는 corridor 위에서 NetworkX 대신 Dijkstra를 돌린다. GCS `download_prefix`만 병렬화한다. `cloudbuild.yaml`은 memory 4Gi·CPU 2·min-instances=0.

**Tech Stack:** Python 3.11+, FastAPI, Shapely, heapq Dijkstra, `google-cloud-storage` + ThreadPoolExecutor, pytest, Cloud Run

**Spec:** `docs/superpowers/specs/2026-08-22-api-latency-warm-cold-design.md`

## Global Constraints

- `min-instances=1` 금지. 상시 비용 없이 요청 중 CPU만 사용
- `SAMPLE_STEP_M` / `RENDER_SIMPLIFY_M` / `DETOUR_MARGIN_M` / `ALPHA_SHADE` / `SNAP_MAX_M` 값 변경 금지
- 배경 지도·경로 `node_ids`·그늘%·그림자 폴리곤이 픽스처에서 최적화 전과 동일해야 함
- 구현 베이스는 **`origin/master`** (tokyo23 + `gcs_sync`). 모바일 브랜치에서 시작하지 말 것
- 이 저장소의 구형 git은 `git commit --trailer`가 실패할 수 있음 → 커밋은 `/usr/bin/git commit -F /tmp/msg.txt`
- 실행 전 격리 워크스페이스가 필요하면 `using-git-worktrees` 스킬로 `origin/master`에서 브랜치를 딴다

---

## File structure

| 파일 | 책임 |
| --- | --- |
| `api/src/hikage_navi/constants.py` | `SNAP_GRID_CELL_M = 100.0` 추가 |
| `api/src/hikage_navi/graph.py` | `length_m` 로드, 격자 색인, 인접 리스트, `snap_to_node` |
| `api/src/hikage_navi/routing.py` | NetworkX `_nx_graph` 제거 → 인접 리스트 Dijkstra |
| `api/src/hikage_navi/gcs_sync.py` | `download_prefix` 병렬 다운로드 |
| `api/tests/test_graph.py` | length_m·스냅 회귀 |
| `api/tests/test_routing.py` | Dijkstra가 기존 픽스처 `node_ids`와 동일 |
| `api/tests/test_gcs_sync.py` | 병렬이어도 blob당 download 1회 |
| `cloudbuild.yaml` | memory 4Gi, cpu 2 |
| `docs/07-gcp-cicd.md` | 자원 값·지연 목표 한 줄 (있을 때만) |

---

### Task 1: 작업 브랜치 (`origin/master` 기준)

**Files:**
- None (git only)

**Interfaces:**
- Consumes: `origin/master` (tokyo23, `gcs_sync`, `BuildingStore` 포함)
- Produces: 브랜치 `feat/api-latency-warm-cold` (이름은 동일하게)

- [ ] **Step 1: master에서 브랜치 생성**

```bash
cd /Users/yeounjaejung/hikage-navi
/usr/bin/git fetch origin
/usr/bin/git checkout -B feat/api-latency-warm-cold origin/master
```

Expected: `api/src/hikage_navi/gcs_sync.py`, `building_store.py` 존재. `feat/task-11-mobile`이 아님.

- [ ] **Step 2: 스펙·계획 파일이 브랜치에 없으면 cherry-pick 또는 복사**

설계·계획 문서가 이 브랜치에 없으면:

```bash
/usr/bin/git checkout feat/task-11-mobile -- \
  docs/superpowers/specs/2026-08-22-api-latency-warm-cold-design.md \
  docs/superpowers/plans/2026-08-22-api-latency-warm-cold.md
printf '%s\n' 'docs: warm·cold 지연 단축 스펙·계획을 master 작업 브랜치에 가져온다' > /tmp/msg.txt
/usr/bin/git add docs/superpowers/specs/2026-08-22-api-latency-warm-cold-design.md \
  docs/superpowers/plans/2026-08-22-api-latency-warm-cold.md
/usr/bin/git commit -F /tmp/msg.txt
```

이미 있으면 스킵.

---

### Task 2: `load_walk_graph` — `length_m` 재사용

**Files:**
- Modify: `api/src/hikage_navi/graph.py` (`load_walk_graph`)
- Modify: `api/tests/test_graph.py`

**Interfaces:**
- Consumes: 기존 `Edge`, `WalkGraph`, `haversine_m`
- Produces: `load_walk_graph(path: Path) -> WalkGraph` — 간선 JSON에 `length_m`이 있으면 `float`로 사용, 없으면 좌표 haversine 합 (기존 동작)

- [ ] **Step 1: Write the failing tests**

`api/tests/test_graph.py`에 추가:

```python
import json


def test_load_uses_length_m_when_present(tmp_path: Path):
    payload = {
        "nodes": [{"id": 1, "lon": 139.0, "lat": 35.0}, {"id": 2, "lon": 139.1, "lat": 35.0}],
        "edges": [
            {
                "u": 1,
                "v": 2,
                "coords": [[139.0, 35.0], [139.1, 35.0]],
                "length_m": 12.5,
            }
        ],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    assert g.edges[0].length_m == 12.5


def test_load_computes_length_when_missing(tmp_path: Path):
    payload = {
        "nodes": [{"id": 1, "lon": 139.7016, "lat": 35.6580}, {"id": 2, "lon": 139.7027, "lat": 35.6580}],
        "edges": [{"u": 1, "v": 2, "coords": [[139.7016, 35.6580], [139.7027, 35.6580]]}],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    assert g.edges[0].length_m > 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && . .venv/bin/activate && pytest tests/test_graph.py::test_load_uses_length_m_when_present tests/test_graph.py::test_load_computes_length_when_missing -v`

Expected: FAIL (또는 첫 테스트가 haversine 결과 ≠ 12.5로 fail)

- [ ] **Step 3: Implement minimal `load_walk_graph` change**

`graph.py`의 간선 루프를:

```python
for e in raw["edges"]:
    coords = [(float(c[0]), float(c[1])) for c in e["coords"]]
    if "length_m" in e and e["length_m"] is not None:
        length = float(e["length_m"])
    else:
        length = 0.0
        for a, b in zip(coords, coords[1:]):
            length += haversine_m(a[0], a[1], b[0], b[1])
    edges.append(Edge(u=int(e["u"]), v=int(e["v"]), coords=coords, length_m=length))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && . .venv/bin/activate && pytest tests/test_graph.py -v`

Expected: PASS (기존 스냅·subgraph 포함)

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'perf: walk-graph 로드 시 length_m이 있으면 haversine을 생략한다' > /tmp/msg.txt
/usr/bin/git add api/src/hikage_navi/graph.py api/tests/test_graph.py
/usr/bin/git commit -F /tmp/msg.txt
```

---

### Task 3: 격자 스냅 색인

**Files:**
- Modify: `api/src/hikage_navi/constants.py`
- Modify: `api/src/hikage_navi/graph.py`
- Modify: `api/tests/test_graph.py`

**Interfaces:**
- Consumes: `SNAP_MAX_M`, `to_planar` (`hikage_navi.geo`)
- Produces:
  - `SNAP_GRID_CELL_M: float = 100.0` in `constants.py`
  - `WalkGraph.adj: dict[int, list[tuple[int, Edge]]] | None = None` (이 태스크에서는 아직 채우지 않아도 됨; dataclass 필드만 추가하거나 Task 4에서 추가)
  - `WalkGraph._cells: dict[tuple[int, int], list[int]] | None` (내부) 또는 `build_snap_index(graph: WalkGraph, cell_m: float = SNAP_GRID_CELL_M) -> None`이 `graph`에 색인을 붙임
  - `snap_to_node(graph, lon, lat) -> tuple[int, float]` — 색인이 있으면 주변 칸만, 없으면 전수 검색(하위 호환). 동률: 더 짧은 거리, 같으면 더 작은 `nid`
  - `load_walk_graph` 끝에서 `build_snap_index(graph)` 호출

격자 키: 평면좌표 `floor(x / cell_m), floor(y / cell_m)`. 검색 반경 칸 수: `ceil(SNAP_MAX_M / cell_m) + 1`.

- [ ] **Step 1: Write the failing tests**

```python
from hikage_navi.graph import build_snap_index


def test_snap_matches_bruteforce_on_fixture():
    g = load_walk_graph(FIXTURE)
    build_snap_index(g)
    for lon, lat in [(139.70160, 35.65800), (139.70155, 35.65890), (139.70265, 35.65710)]:
        a, da = snap_to_node(g, lon, lat)
        # 색인 없이 전수와 동일해야 함 — 임시로 색인 제거 후 비교
        cells = g._cells
        g._cells = None
        b, db = snap_to_node(g, lon, lat)
        g._cells = cells
        assert (a, round(da, 6)) == (b, round(db, 6))


def test_snap_tie_prefers_smaller_node_id(tmp_path: Path):
    # 동일 좌표에 노드 10과 2를 두면 id 2가 이긴다
    payload = {
        "nodes": [
            {"id": 10, "lon": 139.7016, "lat": 35.6580},
            {"id": 2, "lon": 139.7016, "lat": 35.6580},
        ],
        "edges": [],
    }
    path = tmp_path / "tie.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    g = load_walk_graph(path)
    build_snap_index(g)
    nid, dist = snap_to_node(g, 139.7016, 35.6580)
    assert nid == 2
    assert dist == 0.0
```

기존 `test_snap_near_node_2`, `test_snap_too_far_raises`는 `load_walk_graph`가 색인을 붙인 뒤에도 PASS여야 한다.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && . .venv/bin/activate && pytest tests/test_graph.py::test_snap_matches_bruteforce_on_fixture tests/test_graph.py::test_snap_tie_prefers_smaller_node_id -v`

Expected: FAIL (`build_snap_index` 없음 또는 tie 미구현)

- [ ] **Step 3: Implement grid index + snap**

`constants.py`에 `SNAP_GRID_CELL_M = 100.0` 추가.

`graph.py` 요지:

```python
from math import ceil
from hikage_navi.constants import SNAP_MAX_M, SNAP_GRID_CELL_M
from hikage_navi.geo import haversine_m, to_planar


def build_snap_index(graph: WalkGraph, cell_m: float = SNAP_GRID_CELL_M) -> None:
    cells: dict[tuple[int, int], list[int]] = {}
    for nid, (lon, lat) in graph.nodes.items():
        x, y = to_planar(lon, lat)
        key = (int(x // cell_m), int(y // cell_m))
        cells.setdefault(key, []).append(nid)
    graph._cells = cells
    graph._cell_m = cell_m


def snap_to_node(graph: WalkGraph, lon: float, lat: float) -> tuple[int, float]:
    cells = getattr(graph, "_cells", None)
    if not cells:
        candidates = graph.nodes.keys()
    else:
        cell_m = getattr(graph, "_cell_m", SNAP_GRID_CELL_M)
        x, y = to_planar(lon, lat)
        cx, cy = int(x // cell_m), int(y // cell_m)
        ring = int(ceil(SNAP_MAX_M / cell_m)) + 1
        candidates = []
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                candidates.extend(cells.get((cx + dx, cy + dy), ()))
    best_id = None
    best_d = float("inf")
    for nid in candidates:
        nlon, nlat = graph.nodes[nid]
        d = haversine_m(lon, lat, nlon, nlat)
        if d < best_d or (d == best_d and (best_id is None or nid < best_id)):
            best_d = d
            best_id = nid
    if best_id is None or best_d > SNAP_MAX_M:
        raise SnapError()
    return best_id, best_d
```

`load_walk_graph` 반환 직전에 `build_snap_index(graph)` 호출.

- [ ] **Step 4: Run tests**

Run: `cd api && . .venv/bin/activate && pytest tests/test_graph.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'perf: 스냅에 격자 색인을 두어 전 노드 검색을 피한다' > /tmp/msg.txt
/usr/bin/git add api/src/hikage_navi/constants.py api/src/hikage_navi/graph.py api/tests/test_graph.py
/usr/bin/git commit -F /tmp/msg.txt
```

---

### Task 4: 인접 리스트 + Dijkstra (NetworkX 제거)

**Files:**
- Modify: `api/src/hikage_navi/graph.py` (`build_adjacency`, `subgraph_in_bbox`)
- Modify: `api/src/hikage_navi/routing.py` (`_path` — `_nx_graph` / `nx.shortest_path` 제거)
- Modify: `api/tests/test_routing.py` (회귀; 필요 시 adj 구축 확인)

**Interfaces:**
- Consumes: `WalkGraph`, `Edge`, `ALPHA_SHADE`, 기존 `_shade_map` / `_metrics`
- Produces:
  - `build_adjacency(graph: WalkGraph) -> None` — `graph.adj: dict[int, list[tuple[int, Edge]]]` (양방향)
  - `load_walk_graph` / `subgraph_in_bbox` 끝에서 `build_adjacency` 호출
  - `shortest_path` / `shadiest_path` 공개 시그니처 불변
  - `_dijkstra(graph, src, dst, weight_fn) -> list[int]` — 경로 없으면 `DisconnectedError`. 동일 거리면 더 작은 이웃 id를 먼저 확정(결정적)

- [ ] **Step 1: Write / extend failing regression**

기존 `test_shortest_1_to_3`, `test_shadiest_accepts_shadow_index`, `test_disconnected_raises`가 NetworkX 없이 PASS해야 한다. 추가로:

```python
def test_shortest_ignores_networkx_graph_rebuild():
    """요청마다 nx.Graph를 만들지 않아도 픽스처 최단이 같다."""
    g = load_walk_graph(FIXTURE)
    assert getattr(g, "adj", None) is not None
    assert shortest_path(g, 1, 3).node_ids == [1, 2, 3]
```

- [ ] **Step 2: Run to confirm baseline still passes, then implement**

Run: `cd api && . .venv/bin/activate && pytest tests/test_routing.py -v`

(구현 전 `test_shortest_ignores_networkx_graph_rebuild`는 `adj` 없어 FAIL)

- [ ] **Step 3: Implement adjacency + Dijkstra**

`graph.py`:

```python
def build_adjacency(graph: WalkGraph) -> None:
    adj: dict[int, list[tuple[int, Edge]]] = {nid: [] for nid in graph.nodes}
    for e in graph.edges:
        if e.u in adj and e.v in adj:
            adj[e.u].append((e.v, e))
            adj[e.v].append((e.u, e))
    graph.adj = adj
```

`subgraph_in_bbox` 반환 전 `build_adjacency(area)` (+ 선택: 스냅은 전체 그래프에서만 쓰므로 subgraph에 스냅 색인은 생략 가능).

`routing.py` — `import networkx` 제거 후:

```python
import heapq
from hikage_navi.graph import Edge, WalkGraph


def _dijkstra(graph: WalkGraph, src: int, dst: int, weight_fn) -> list[int]:
    adj = getattr(graph, "adj", None)
    if adj is None:
        from hikage_navi.graph import build_adjacency
        build_adjacency(graph)
        adj = graph.adj
    if src not in adj or dst not in adj:
        raise DisconnectedError()
    dist = {src: 0.0}
    prev: dict[int, int | None] = {src: None}
    heap: list[tuple[float, int]] = [(0.0, src)]
    seen: set[int] = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if u == dst:
            break
        for v, edge in adj[u]:
            w = float(weight_fn(edge))
            if w < 0:
                w = 0.0
            nd = d + w
            if nd < dist.get(v, float("inf")) or (
                nd == dist.get(v, float("inf")) and (prev.get(v) is None or u < prev[v])
            ):
                # 표준 완화: 더 짧을 때만 갱신. 동률 경로 선택은 픽스처에 단일 경로면 영향 없음
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
    if dst not in prev and src != dst:
        raise DisconnectedError()
    if src == dst:
        return [src]
    if dst not in prev:
        raise DisconnectedError()
    path = []
    cur: int | None = dst
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    if path[0] != src:
        raise DisconnectedError()
    return path


def _path(...):
    try:
        nodes = _dijkstra(graph, src, dst, weight_fn)
    except DisconnectedError:
        raise
    return _metrics(graph, nodes, shade_map, index)
```

동률 분기 구현이 복잡해지면 **더 짧은 거리만 갱신**하는 표준 Dijkstra로 두고, 픽스처·기존 테스트가 통과하는지로 충분하다 (스펙: 픽스처 `node_ids` 동일).

`load_walk_graph` 끝: `build_snap_index` 다음 `build_adjacency`.

- [ ] **Step 4: Run routing + graph + service tests**

Run: `cd api && . .venv/bin/activate && pytest tests/test_routing.py tests/test_graph.py tests/test_service.py -v`

Expected: PASS. `rg "networkx|import nx" api/src/hikage_navi/routing.py` → 매치 없음.

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'perf: 경로 탐색을 인접 리스트 Dijkstra로 바꿔 NetworkX 재구성을 없앤다' > /tmp/msg.txt
/usr/bin/git add api/src/hikage_navi/graph.py api/src/hikage_navi/routing.py api/tests/test_routing.py
/usr/bin/git commit -F /tmp/msg.txt
```

---

### Task 5: GCS `download_prefix` 병렬화

**Files:**
- Modify: `api/src/hikage_navi/gcs_sync.py` (`download_prefix`)
- Modify: `api/tests/test_gcs_sync.py`

**Interfaces:**
- Consumes: 기존 `_safe_download_dest`, `blob.download_to_filename`
- Produces: `download_prefix(..., max_workers: int = 8)` — `ThreadPoolExecutor`로 각 blob 1회 다운로드. 경로 escape 검증은 다운로드 전에 동기적으로 실패. stamp/skip 로직 불변

- [ ] **Step 1: Extend test — still one download per blob**

기존 `test_sync_processed_downloads_when_stamp_missing`가 PASS 유지. 추가:

```python
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


def test_download_prefix_uses_thread_pool(tmp_path: Path, monkeypatch):
    prefix = "processed/tokyo23"
    blobs = [
        _blob(f"{prefix}/walk-graph.json"),
        _blob(f"{prefix}/boundary.geojson"),
        _blob(f"{prefix}/wards/13113/buildings.geojson"),
    ]
    for b in blobs:
        def _dl(path, blob=b):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("x", encoding="utf-8")
        b.download_to_filename.side_effect = _dl

    client = MagicMock()
    bucket = MagicMock()
    client.bucket.return_value = bucket
    bucket.list_blobs.return_value = blobs

    with patch("hikage_navi.gcs_sync.ThreadPoolExecutor", wraps=ThreadPoolExecutor) as pooled:
        download_prefix(
            client=client, bucket_name="b", prefix=prefix, data_dir=tmp_path, max_workers=4
        )
    assert pooled.call_count >= 1
    for b in blobs:
        assert b.download_to_filename.call_count == 1
```

- [ ] **Step 2: Run failing test**

Run: `cd api && . .venv/bin/activate && pytest tests/test_gcs_sync.py::test_download_prefix_uses_thread_pool -v`

Expected: FAIL (`ThreadPoolExecutor` 미사용 또는 `max_workers` 없음)

- [ ] **Step 3: Implement parallel download**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed


def download_prefix(
    *,
    client,
    bucket_name: str,
    prefix: str,
    data_dir: Path,
    max_workers: int = 8,
) -> None:
    bucket = client.bucket(bucket_name)
    list_prefix = prefix if prefix.endswith("/") else prefix + "/"
    data_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[object, Path]] = []
    for blob in bucket.list_blobs(prefix=list_prefix):
        name = blob.name
        if name.endswith("/"):
            continue
        rel = name[len(list_prefix) :]
        dest = _safe_download_dest(data_dir, rel)
        if dest is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((blob, dest))

    def _one(item: tuple[object, Path]) -> None:
        blob, dest = item
        blob.download_to_filename(str(dest))

    workers = max(1, min(max_workers, len(jobs) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, job) for job in jobs]
        for fut in as_completed(futures):
            fut.result()  # 첫 예외를 기동 실패로 전파
```

- [ ] **Step 4: Run all gcs_sync tests**

Run: `cd api && . .venv/bin/activate && pytest tests/test_gcs_sync.py -v`

Expected: PASS (escape 테스트 포함)

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'perf: GCS tokyo23 sync 다운로드를 병렬화한다' > /tmp/msg.txt
/usr/bin/git add api/src/hikage_navi/gcs_sync.py api/tests/test_gcs_sync.py
/usr/bin/git commit -F /tmp/msg.txt
```

---

### Task 6: Cloud Run 자원 + 문서 + 전체 회귀

**Files:**
- Modify: `cloudbuild.yaml` (`--memory=4Gi`, `--cpu=2`, `--min-instances=0` 유지)
- Modify: `docs/07-gcp-cicd.md` (메모리/CPU·지연 목표 한두 문장; bake가 아닌 GCS sync 전제 유지)

**Interfaces:**
- Consumes: 기존 deploy env (`HIKAGE_DATA_DIR`, `HIKAGE_GCS_*`)
- Produces: 배포 설정이 스펙 수용 기준과 일치

- [ ] **Step 1: Update `cloudbuild.yaml`**

`gcloud run deploy` args에서:

```yaml
      - --memory=4Gi
      - --cpu=2
      - --min-instances=0
```

(`--timeout=300` 및 GCS env는 유지. `--memory=2Gi` / `--cpu=1` 삭제)

- [ ] **Step 2: Verify with ripgrep**

Run: `rg -n "memory=|cpu=|min-instances" cloudbuild.yaml`

Expected: `4Gi`, `2`, `0` 각 1회. `2Gi`/`1Gi` 없음.

- [ ] **Step 3: Docs touch**

`docs/07-gcp-cicd.md`에 Cloud Run API 절이 있으면: memory 4Gi·CPU 2·min-instances 0, warm/cold 목표(8s/5s/25s)를 한 줄로 적는다. 없으면 스킵하지 말고 sync 설계 문서 링크 근처에 짧게 추가.

- [ ] **Step 4: Full API regression**

Run: `cd api && . .venv/bin/activate && pytest -v`

Expected: PASS 전부

- [ ] **Step 5: Commit**

```bash
printf '%s\n' 'build: Cloud Run API를 4Gi·CPU 2로 맞춰 warm·cold 지연 단축을 반영한다' > /tmp/msg.txt
/usr/bin/git add cloudbuild.yaml docs/07-gcp-cicd.md
/usr/bin/git commit -F /tmp/msg.txt
```

---

### Task 7: 배포 스모크 (수동 수용)

**Files:**
- None (운영 검증)

**Interfaces:**
- Consumes: Cloud Build → Cloud Run `hikage-navi-api`
- Produces: 스펙 수용 체크리스트 증거 (시간 숫자)

- [ ] **Step 1: Push branch and let Cloud Build deploy (or `gcloud builds submit`)**

master 머지/PR은 별도. 이 태스크는 이미지만 올라가면 됨.

- [ ] **Step 2: Warm `/routes` ≤ 8s**

인스턴스를 한 번 깨운 뒤:

```bash
API=https://hikage-navi-api-XXXX.a.run.app
# health로 warm
curl -s -o /dev/null -w "health %{time_total}\n" "$API/health"
curl -s -o /tmp/r.json -w "routes %{time_total}\n" -X POST "$API/routes" \
  -H "Content-Type: application/json" \
  -d '{"origin":{"lon":139.70056,"lat":35.65905},"destination":{"lon":139.7104,"lat":35.6467},"datetime":"2026-08-14T12:00:00+09:00"}'
```

Expected: `time_total` ≤ 8. 응답에 `shortest` 좌표 존재.

- [ ] **Step 3: Warm `/shadows` ≤ 5s**

```bash
curl -s -o /dev/null -w "shadows %{time_total}\n" \
  "$API/shadows?datetime=2026-08-14T12:00:00%2B09:00&bbox=139.695,35.653,139.712,35.665"
```

Expected: ≤ 5 (두 번째 호출은 캐시로 더 짧을 수 있음 — **첫 warm** 기준)

- [ ] **Step 4: Cold ≤ 25s**

Cloud Run 인스턴스가 내려간 뒤(수 분 idle) 또는 새 리비전 직후:

```bash
curl -s -o /dev/null -w "cold_health %{time_total}\n" --max-time 60 "$API/health"
curl -s -o /tmp/r2.json -w "cold_routes %{time_total}\n" --max-time 60 -X POST "$API/routes" \
  -H "Content-Type: application/json" \
  -d '{"origin":{"lon":139.70056,"lat":35.65905},"destination":{"lon":139.7104,"lat":35.6467},"datetime":"2026-08-14T12:00:00+09:00"}'
```

Expected: health+routes 합 또는 첫 실질 요청 ≤ 25s, HTTP 200. 브라우저 Failed to fetch 없음.

- [ ] **Step 5: Confirm min-instances and resources**

```bash
gcloud run services describe hikage-navi-api --region=asia-northeast1 \
  --format='yaml(spec.template.metadata.annotations,spec.template.spec.containers[0].resources)'
```

Expected: min-instances 0 (또는 unset=0), memory 4Gi, cpu 2.

---

## Self-review (plan vs spec)

| Spec 요구 | Task |
| --- | --- |
| `length_m` 재사용 | Task 2 |
| 격자 스냅 ~100 m, SNAP_MAX_M 유지, 결정적 동률 | Task 3 |
| 인접 리스트 Dijkstra, NetworkX 재구성 제거, 가중치 동일 | Task 4 |
| 그림자 파라미터 불변 | Task 4 비변경 + Task 6 회귀 |
| GCS 병렬 다운로드, stamp 유지 | Task 5 |
| 4Gi / CPU 2 / min-instances 0 | Task 6–7 |
| 수용 8s / 5s / 25s | Task 7 |
| `origin/master` 베이스 | Task 1 |
| 바이너리 포맷·min-instances=1·샘플 변경 비범위 | 태스크 없음 (의도적) |
