# 지도 위 유리 UI — 설계

상태: 확정 (대화에서 A 방향·레이아웃·시트 정보 승인 후 작성)  
기준 커밋: `master` `1415dad` (연속 직사광선·급수 포함)  
관련: [docs/03-ui-spec.md](../../03-ui-spec.md)

## 1. 목적

한손 스마트폰에서 지도를 가장 크게 두고, 기본 HTML 패널처럼 보이지 않게 한다.  
S0–S5, 일본어 문안, `/boundary`·`/shadows`·`/routes` 계약은 바꾸지 않는다.

성공:

- 폭 ≈375px에서 지도가 화면의 주인공이다. peek 시트가 지도의 40%를 넘지 않는다.
- 출발→도착→探す→경로 비교가 데스크톱과 같은 상태 기계로 동작한다.
- 터치 타깃 ≥44px, `env(safe-area-inset-*)`로 노치·홈 인디케이터에 가리지 않는다.
- `prefers-reduced-motion: reduce`이면 모션을 끈다.

## 2. 레이아웃

지도가 `#root` 전체를 채운다. 크롬은 위에 얹는다.

| 조각 | 위치 | 역할 |
| --- | --- | --- |
| 상단 알약 | 좌상단, safe-area 아래 | `日陰ナビ` + 夜間 뱃지 + `datetime-local` |
| 범례 칩 | 우상단 | 最短 / 日陰 / 給水スポット 토글 |
| 現在地 FAB | 우하단, 시트 위 | 구 안이면 출발로 설정 (기존 로직) |
| 바텀 시트 | 하단 | peek / half / expanded |

데스크톱(≥900px): 시트를 왼쪽 유리 레일(~340px)로 띄운다. 지도를 그리드로 쪼개지 않는다.

`datetime-local`은 네이티브 피커를 유지한다. 커스텀 달력을 만들지 않는다.

## 3. 시트 스냅

| 스냅 | 높이 | 내용 |
| --- | --- | --- |
| peek | 핸들 + 한 줄, 약 88px + safe-area | CTA 또는 선택 경로 요약 |
| half | `min(38vh, 320px)` | 카드 비교, 連続直射日光, 探す/やり直す |
| expanded | `min(52vh, 480px)`, 넘치면 스크롤 | half + 出典 |

- 핸들을 위로 끌거나 peek 본문을 탭하면 peek→half→expanded.
- 지도를 탭해 핀을 찍으면 peek로 내린다. 경로는 지우지 않는다(기존 MAP_TAP 규칙).
- 計算中이면 시트를 peek에 고정하고 `ルートを計算しています`.

## 4. Peek 한 줄

| 상태 | Peek |
| --- | --- |
| 로딩 | `ルートを計算しています` |
| S0 | `地図をタップして出発地点を選んでください` |
| S1 | `次に到着地点をタップしてください` (`copy.peekS1`) |
| S2 | 버튼 `ルートを探す` (한 줄 높이) |
| S3 | `{最短\|日陰} {formatPath(selected)}` |
| S4 | `夜間 · 最短 {m}m · {min}分` |
| S5 | `errorMessage` + `閉じる` |

half에서 S0는 `s0sub`를 추가로 보여 준다. S1는 기존 `s1` + `出発をやり直す`.

급수 목록은 시트에 넣지 않는다. 지도 마커 + 범례 토글만.

## 5. 경로 카드와 링

S3 half: 최단/그늘 카드 두 장(동일 루트면 한 장 + `同じルートです`).

각 카드:

- 왼쪽: 그늘 % 링 하나. 지름 44px. 최단=`--short`, 그늘=`--shade`.
- 오른쪽: `formatPath` + `formatContinuousSun`.
- 선택 카드: 테두리 `--accent`.

야간(S4): 링 없음. 그늘%·연속 직사광선을 보여 주지 않는다.

거리·시간·연속 직사광선용 차트는 두지 않는다.

Bklit UI 링 차트는 shadcn/Tailwind 전제가 커서 **이번 브랜치에는 넣지 않는다.** 대신 Bklit 링과 같은 역할(원형 트랙 + % 아크 + 중앙 숫자)을 `ShadeRing` CSS로 구현한다. 색은 `--short` / `--shade` 토큰만 쓴다.

## 6. 시각 토큰

- 유리: `background: color-mix(in srgb, white 82%, transparent); backdrop-filter: blur(16px)`.
- 모서리: 알약 999px, 시트 상단 16px, 카드·버튼 12px.
- 지도 핀: 기존 출발/도착 색 유지, `border-radius: 999px`.
- 본문 글꼴: 기존 JP 산세리프. 장식용 모노스페이스·네온은 쓰지 않는다.
- 다크 테크 배경(anime.js/Bklit 랜딩) 금지. 야외 가독성.

## 7. 모션 (anime.js)

`animejs`만 추가한다. 움직이는 것:

- 시트 높이 peek↔half↔expanded (220ms, ease-out).
- S3 카드가 처음 나타날 때 opacity 0→1 (stagger 40ms, 합 160ms 이하).

하지 않는 것: 경로 GeoJSON을 SVG로 다시 그리기, 스크롤 패럴랙스, 상시 루프 애니메이션.

`prefers-reduced-motion: reduce`이면 `anime.remove` 후 높이를 CSS로 즉시 설정한다.

## 8. 접근

- 버튼·알약 입력·FAB·범례 체크 `min-height: 44px`.
- 시트 핸들 `aria-label="シート"`, `aria-expanded`.
- 색만으로 최단/그늘을 구분하지 않는다. 범례 라벨 유지.
- 出典는 expanded(데스크톱 레일 하단)에서 항상 읽을 수 있다.

## 9. 하지 않는 것

장소 검색, 페이지 분리, 커스텀 달력, Tailwind/shadcn 도입, 라우팅 가중치 변경, 23区 확대.

## 10. 테스트

순수 함수로 검증한다 (Vitest, 기존 `environment: node`).

- `peekHeadline(state, loading)`
- `selectedPath(state)`
- `clampShadePct`
- `sheetAfterMapTap` → 항상 `"peek"`
- `advanceSheetSnap`: peek→half→expanded→peek

레이아웃·블러는 수동(DevTools 375×812). 기존 `api.test.ts` / `state.test.ts`는 깨지지 않아야 한다.
