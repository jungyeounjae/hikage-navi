# 기술 선택 — hikage-navi v0.1

상태: 확정 (파일럿 기본값)  
관련: [01-requirements.md](01-requirements.md), [04-data-algorithm.md](04-data-algorithm.md), [07-gcp-cicd.md](07-gcp-cicd.md)

## 결론

| 층 | 언어 / 도구 | v0.1 |
| --- | --- | --- |
| 프론트 | **TypeScript** + React + Vite + MapLibre GL JS | 로컬에서 개발 |
| 서버 | **Python** + FastAPI | 로컬에서 개발 |
| 전처리 | **Python** (같은 코드베이스) | 로컬에서 한 번 |
| 데이터 저장 | 파일 (GeoJSON, 그래프). DB 없음 | 로컬 `data/` → 배포 시 api 이미지에 포함 |
| 웹 배포 | **Vercel** (Vite 정적 사이트) | 프론트만 |
| API 배포·학습 | **GCP**: Cloud Build → Artifact Registry → Cloud Run | API Docker 이미지 |

앱을 만들고 검증하는 곳은 노트북이다.  
웹은 **Vercel**, API는 **GCP Cloud Run**에 올린다. GCP는 API 이미지·CI/CD 학습용이다. 상세는 [07-gcp-cicd.md](07-gcp-cicd.md).

## 프론트: TypeScript

지도는 브라우저에서 돌아가야 하므로 JavaScript 계열이 필수다.  
타입과 이후 확장을 위해 **TypeScript**를 쓴다.

- UI: React. 화면이 하나라 Next.js는 쓰지 않는다. Vite SPA면 충분하다.
- 지도: MapLibre GL JS. 국토지리원 타일을 그냥 붙일 수 있고 과금이 없다.
- 역할: 핀, 시각 선택, 선·그림자 그리기, 서버에 경로 요청. **그림자 기하와 다익스트라는 프론트에서 하지 않는다.**

Node/Turf.js로 그림자를 프론트에서 계산하는 방법도 있으나, 시부야 건물 전량은 브라우저에 무겁다. v0.1에서는 서버에 맡긴다.

## 서버: Python

그늘 계산이 GIS 작업이다. Python 쪽에 이미 도구가 있다.

- API: FastAPI
- 그림자: pybdshadow 또는 Shapely로 동일 규약 구현
- 경로: NetworkX (또는 OSMnx로 만든 그래프)
- 전처리: plateaukit 등 CityGML → GeoJSON, OSM clip

로그인·세션·DB는 없다. 요청이 오면 메모리에 올린 그래프와 건물로 계산해 JSON을 돌려준다. 전처리와 API는 같은 Python으로 둔다.

## 클라우드

앱 실행에 GCP가 필수는 아니다. 로컬 구성은 아래와 같다.  
배포는 웹=Vercel, API=Cloud Build → Artifact Registry → Cloud Run. 상세는 [07-gcp-cicd.md](07-gcp-cicd.md).

필요한 외부 호스트는 지도 타일이다.

- 국토지리원 타일: 브라우저가 직접 받는다. 우리 서버를 거치지 않는다.
- PLATEAU / OSM 원본: 개발할 때 한 번 받아 전처리 파일로 남긴다.

## 로컬에서 돌아가는 모양

```
개발자 노트북
  Vite (TS)     :5173  지도 UI
  FastAPI (Py)  :8000  /routes, /shadows
  data/         전처리된 시부야 건물·보행망
브라우저 ------ 국토지리원 타일 (인터넷)
```

인터넷이 필요한 것은 지도 타일뿐이다. 경로·그림자는 로컬 서버가 계산한다.

## 쓰지 않는 것 (이 버전)

- Next.js, 네이티브 앱
- Node를 경로/그림자 엔진으로 쓰는 구성
- PostgreSQL / PostGIS / Redis
- GKE, Cloud SQL, Terraform, AWS, Azure
- 프론트를 GCP에 올리는 구성 (웹은 Vercel)
- 공개 Nominatim / 공개 OSRM 데모
