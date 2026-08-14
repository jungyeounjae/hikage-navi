# hikage-navi (日陰ナビ)

시부야구 보행자를 위한 **그늘 길찾기** 파일럿입니다.

한국의 [그늘로](https://ttubeok.com/)를 참고하되, 대중교통·버스 창가·가로수는 넣지 않습니다.  
시부야구 안에서 출발·도착을 찍으면 **최단 도보**와 **그늘이 더 많은 도보**를 비교합니다.

현재는 **사양 단계**입니다. 앱 코드는 아직 없습니다.

## 하는 일 (v0.1)

- 시부야구 지도에 시간대별 건물 그림자 표시
- 지도 탭으로 출발·도착 지정
- 최단 경로 vs 그늘 경로 (거리, 시간, 그늘 %)
- 밤에는 최단 경로만

## 쓰지 않는 것

전철·버스, 창가 추천, 가로수, 지하가, 장소 검색, 네이티브 앱, 로그인.

## 기술

| 층 | 선택 |
| --- | --- |
| 웹 | TypeScript, React, Vite, MapLibre |
| API | Python, FastAPI |
| 웹 배포 | Vercel |
| API 배포 | Cloud Build → Artifact Registry → Cloud Run |

개발은 노트북에서 합니다. Docker·GCP·Vercel은 앱이 로컬에서 된 뒤에 붙입니다.

## 사양

구현은 아래 문서를 기준으로 합니다.

| 문서 | 내용 |
| --- | --- |
| [docs/01-requirements.md](docs/01-requirements.md) | 요건 정의 |
| [docs/02-functional-spec.md](docs/02-functional-spec.md) | 기능 사양 |
| [docs/03-ui-spec.md](docs/03-ui-spec.md) | 화면 사양 |
| [docs/04-data-algorithm.md](docs/04-data-algorithm.md) | 데이터·알고리즘 |
| [docs/05-acceptance.md](docs/05-acceptance.md) | 수용 기준 |
| [docs/06-tech-stack.md](docs/06-tech-stack.md) | 기술 선택 |
| [docs/07-gcp-cicd.md](docs/07-gcp-cicd.md) | Vercel / GCP CI/CD |

## 데이터 출처

- 지도: [국토지리원](https://maps.gsi.go.jp/development/ichiran.html)
- 건물: [Project PLATEAU](https://www.mlit.go.jp/plateau/) (渋谷区)
- 도로: [OpenStreetMap](https://www.openstreetmap.org/copyright)

## 상태

- [x] 요건·기능 사양
- [ ] 로컬 웹 + API
- [ ] Docker (API)
- [ ] Cloud Run + Artifact Registry
- [ ] Vercel
