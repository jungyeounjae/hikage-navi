# GCE 전처리 + GCS 보관 설계

상태: 확정 (2026-08-20)  
관련: [docs/07-gcp-cicd.md](../../07-gcp-cicd.md), Task 13–14

## 목표

Mac에 `data/raw`(CityGML ZIP·압축 해제)를 두지 않는다.  
전처리는 **필요할 때만 켜는 GCE VM**에서 돌리고, 산출물·raw는 **GCS를 정식 보관소**로 둔다.

## 역할

| 위치 | 역할 |
| --- | --- |
| GCE VM (`hikage-preprocess`) | 작업장. `preprocess.py` 실행. 평소는 **중지** |
| GCS `gs://<project>-hikage-navi/` | 정식 보관: `raw/`, `processed/tokyo23/` |
| Mac | 코드만. raw 금지. 로컬 API 검증 시에만 `processed/tokyo23`을 GCS에서 동기화 |

## 버킷 레이아웃

```
gs://<project>-hikage-navi/
  raw/                      # ZIP, citygml_* 해제본, osmnx_cache
  processed/tokyo23/        # boundary, walk-graph, wards/, water-spots
```

## VM

- Region/zone: `asia-northeast1-a`
- Machine: `e2-standard-4`
- Boot disk: 200GB SSD, Ubuntu 22.04
- Lifecycle: start → work → `gsutil rsync` → **stop**

## 비범위

- Terraform / Cloud Run Job
- BuildingStore → GCS 런타임 연동 (배포 2차)
- 웹을 GCP에 올리는 것 (Vercel 유지)

## 성공 기준

- [ ] 문서만 보고 VM 생성·전처리·GCS 동기화·중지가 가능하다
- [ ] Mac에서 `data/raw`를 지워도 재전처리 경로가 있다
- [ ] 헬퍼 스크립트가 start / sync-up / sync-down / stop을 제공한다
