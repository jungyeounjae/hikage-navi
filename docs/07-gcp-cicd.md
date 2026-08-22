# 배포 · CI/CD — hikage-navi v0.1

상태: 확정  
관련: [06-tech-stack.md](06-tech-stack.md)

앱 기능은 노트북만으로 돌아간다.  
배포는 **웹=Vercel**, **API=GCP** 로 나눈다.

## 1. 왜 나누는가

Vite + React 프론트는 정적 파일이라 Vercel이 가장 단순하다.  
그늘·경로 API는 Python + 메모리 그래프라 Vercel 서버리스에 맞지 않는다. (시간 제한, 콜드 스타트, 이미지 용량)

GCP에서 배우고 싶은 것(CI/CD, Artifact Registry)은 **API 이미지 한 장**으로 충분하다. 웹까지 Docker로 올리면 학습은 늘지만 운영만 복잡해진다.

```
테스트: git push → GitHub Actions (pytest + vitest)
프론트: git push → Vercel (정적 사이트)
API:    git push → Cloud Build → Artifact Registry → Cloud Run
```

## 2. 웹: Vercel

- 프레임워크: Vite SPA. Next.js로 바꾸지 않는다.
- 빌드: `npm run build` → `dist/`
- 환경 변수: `VITE_API_BASE_URL` = Cloud Run API URL
- GitHub 저장소를 Vercel 프로젝트에 연결. `main` push 시 자동 배포.
- Hobby 플랜으로 파일럿 가능. Vercel 계정 가입 필요. (GCP와 별개)

브라우저가 국토지리원 타일은 직접 받고, 경로 요청만 Vercel에 올라간 JS가 Cloud Run API로 보낸다.

## 3. API: GCP

| 서비스 | 역할 |
| --- | --- |
| **Artifact Registry** | `api` Docker 이미지만 저장 |
| **Cloud Build** | API 빌드·푸시·Cloud Run 배포 |
| **Cloud Run** | FastAPI 실행. min-instances 0, memory 4Gi, CPU 2, `asia-northeast1` |

아티팩트:

```
asia-northeast1-docker.pkg.dev/<PROJECT>/hikage-navi/api:<git-sha>
```

전처리 **산출물**(`processed/tokyo23`)은 **이미지에 넣지 않는다**. Cloud Run 기동 시 `hikage_navi.gcs_sync`가 `gs://hikage-navi-data/processed/tokyo23`을 `/data/tokyo23`으로 받는다.

Cloud Run 런타임 서비스 계정에는 버킷 `hikage-navi-data`에 대해 `roles/storage.objectViewer`가 필요하다. 배포 env는 `HIKAGE_DATA_DIR`, `HIKAGE_GCS_PROCESSED_URI`, `HIKAGE_GCS_SYNC`다.

지연 목표(warm): `/routes` ≤ 8s, `/shadows` ≤ 5s. 콜드 첫 요청(GCS sync + 그래프 로드) ≤ 25s. 상세는 [2026-08-22-api-latency-warm-cold-design.md](superpowers/specs/2026-08-22-api-latency-warm-cold-design.md).

**raw**(CityGML ZIP·압축 해제)는 Mac에 두지 않고 GCE VM + GCS에서 관리한다. 절차는 [08-gce-preprocess.md](08-gce-preprocess.md).

쓰지 않는 것: GKE, Cloud SQL, 웹 Docker 이미지, Terraform.

## 4. CI/CD

### Vercel (웹)

`main` push → 설치 → 빌드 → 배포. Vercel 대시보드에서 연결하면 된다.  
별도 `Dockerfile.web`은 없다.

### GitHub Actions (테스트)

`master` push 및 pull request 시 `.github/workflows/test.yml`이 돈다.

1. API: `pip install -e ".[dev]"` → `pytest tests/` (픽스처 데이터)
2. 웹: `npm ci` → `npm test`

테스트가 실패해도 Cloud Build·Vercel 배포는 **따로** 돈다. 배포를 막으려면 GitHub 브랜치 보호에서 이 워크플로를 필수 검사로 두면 된다.

### Cloud Build (API)

`master` push 시:

1. `api` 이미지 빌드 → Artifact Registry
2. Cloud Run `hikage-navi-api` 새 리비전

구현 파일: `Dockerfile.api`, `cloudbuild.yaml`

CORS: api는 Vercel origin만 허용. (`https://<project>.vercel.app` 및 커스텀 도메인이 있으면 그것)

## 5. 로컬 vs 배포

```
로컬:  브라우저 → Vite :5173 → FastAPI :8000
배포:  브라우저 → Vercel     → Cloud Run API
              ↘ 국토지리원 타일
```

## 6. 개발 순서

1. 로컬에서 지도·그늘·경로가 돈다 (시부야 fixtures 또는 GCS에서 받은 tokyo23)
2. 23区 raw·전처리는 GCE에서 ([08-gce-preprocess.md](08-gce-preprocess.md))
3. API Dockerfile로 로컬 `docker run`이 된다
4. GCP: Artifact Registry + Cloud Run에 API를 올린다
5. Vercel에 웹을 올리고 `VITE_API_BASE_URL`을 Cloud Run URL로 넣는다
6. Cloud Build로 API 배포를 자동화한다

1이 끝나기 전에 Vercel/Cloud Run을 붙이지 않는다. GCE 전처리 버킷·VM은 데이터 준비용으로 먼저 둬도 된다.

## 7. 사람이 준비할 계정

- **Vercel**: 웹 배포. 결제 없이 Hobby로 시작 가능
- **GCP**: 프로젝트 + 결제 계정. Cloud Build, Artifact Registry, Cloud Run 활성화
- 저장소에 GCP/Vercel 키 파일을 넣지 않는다

## 8. 수용 (배포 층)

앱 수용기준([05-acceptance.md](05-acceptance.md))과는 별도다.

- [ ] Vercel URL을 열면 시부야 지도가 나온다
- [ ] 그 페이지에서 경로 탐색이 Cloud Run API를 친다
- [ ] `main` push 후 Cloud Build가 성공한다
- [ ] Artifact Registry에 `api` 이미지가 SHA 태그로 있다
- [ ] 저장소에 클라우드 키 파일이 없다
