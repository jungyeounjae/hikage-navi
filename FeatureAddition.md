# hikage-navi — 연속 직사광선 노출 + 급수 스팟 표시 기능 추가

기존 `hikage-navi` 프로젝트에 다음 두 기능을 추가해주세요.

1. **경로에서 최대 연속 직사광선 노출 거리/시간 계산**
2. **선택된 경로 주변의 급수 가능한 장소 표시**

이번 단계에서는 기존 Routing Algorithm 자체를 크게 변경하지 않고, 사용자가 현재 경로의 **더위 위험도와 급수 가능 여부를 함께 판단할 수 있도록 정보를 확장**하는 것이 목적입니다.

---

# 1. 최대 연속 직사광선 노출 계산

현재 보행 경로의 각 구간을 일정 간격으로 sampling하여 `SUN / SHADE`를 판정하고 있으므로 기존 데이터를 그대로 활용해주세요.

예를 들어:

```text
SUN   5m
SUN   5m
SHADE 5m
SUN   5m
SUN   5m
SUN   5m
SHADE 5m

```

라면:

```text
max_continuous_sun_m = 15

```

가 되어야 합니다.

기존 프로젝트에서 사용하는 평균 보행 속도를 재사용하여 다음 값도 계산해주세요.

```text
max_continuous_sun_seconds

```

새로운 보행 속도 상수를 중복 정의하지 마세요.

---

# 2. Edge 경계를 넘는 연속 노출 고려

각 Edge별 최대값을 따로 계산해서는 안 됩니다.

예:

```text
Edge A
SHADE
SUN
SUN

Edge B
SUN
SUN
SHADE

```

실제 보행에서는 Edge A 마지막과 Edge B 처음의 SUN이 하나의 연속된 직사광선 구간입니다.

따라서 전체 Route의 이동 순서를 기준으로 계산해주세요.

개념적으로는:

```text
currentContinuousSunDistance
maxContinuousSunDistance

```

를 관리하면 됩니다.

SUN:

```text
currentContinuousSunDistance += sampleDistance

```

SHADE:

```text
currentContinuousSunDistance = 0

```

그리고:

```text
maxContinuousSunDistance =
  max(maxContinuousSunDistance, currentContinuousSunDistance)

```

현재 구조에 더 자연스러운 구현 방법이 있다면 기존 구조를 우선해주세요.

---

# 3. Route 결과에 지표 추가

기존 Route 정보에 다음 필드를 추가해주세요.

```text
max_continuous_sun_m
max_continuous_sun_seconds

```

예:

```json
{
  "distance_m": 1260,
  "duration_seconds": 920,
  "shade_pct": 78,
  "shade_m": 983,
  "sun_m": 277,
  "max_continuous_sun_m": 24,
  "max_continuous_sun_seconds": 18
}
```

기존 API 구조를 깨지 않도록 additive하게 추가해주세요.

---

# 4. 연속 직사광선 UI 표시

현재 경로 결과에서 거리, 시간, 그늘 비율 등을 표시하는 영역에 다음 정보를 추가해주세요.

```text
直射日光の連続時間 最大18秒

```

UI 공간이 부족하면:

```text
連続直射日光 最大18秒

```

으로 표현해도 됩니다.

여러 경로를 비교하는 경우 각각의 값을 표시하여 사용자가

```text
그늘 비율은 비슷하지만
연속해서 햇빛에 노출되는 시간이 더 짧은 경로

```

를 판단할 수 있도록 해주세요.

기존 UI 디자인과 컴포넌트를 유지해주세요.

---

# 5. 급수 스팟 데이터 추가

사용자가 현재 선택한 경로 주변에서 물을 마시거나 마이보틀에 급수할 수 있는 장소를 지도에 표시하고 싶습니다.

우선 다음 데이터 소스를 대상으로 구현해주세요.

### OpenStreetMap

최소한 다음 태그를 활용해주세요.

```text
amenity=drinking_water

```

가능하다면 다음 정보도 함께 활용해주세요.

```text
drinking_water=yes
bottle=*
access=*
opening_hours=*
indoor=*

```

기존 프로젝트가 사용하고 있는 OSM 데이터 조회/처리 방식을 최대한 재사용해주세요.

---

# 6. WaterSpot 모델

급수 데이터를 내부에서는 하나의 공통 구조로 관리할 수 있도록 해주세요.

예:

```text
WaterSpot

id
name
lat
lon
type
source
bottle_refill
access
opening_hours

```

`type`은 MVP에서는 지나치게 세분화하지 않아도 됩니다.

예:

```text
DRINKING_WATER
BOTTLE_REFILL

```

`source`는 향후 공식 지자체 데이터를 추가할 수 있도록 확장 가능하게 해주세요.

예:

```text
OSM
TOKYO_WATER
LOCAL_GOVERNMENT

```

단, 이번 구현에서 실제로 사용하지 않는 데이터 소스까지 불필요한 처리 코드를 미리 만들지는 마세요.

과도한 abstraction은 피해주세요.

---

# 7. 급수 스팟은 현재 선택된 Route 주변만 표시

지도 전체에 모든 급수소를 표시하지 마세요.

현재 선택된 Route를 기준으로 주변에 있는 WaterSpot만 검색해주세요.

개념적으로:

```text
Selected Route Polyline
        ↓
Route 주변 Buffer
        ↓
WaterSpot 검색
        ↓
경로 주변 급수소만 지도에 표시

```

초기 MVP에서는 Route에서 약 **50m 이내**의 급수 스팟을 대상으로 해주세요.

다만 기존 프로젝트의 지도 스케일이나 좌표 처리 방식상 더 적절한 값이 있다면 조정 가능합니다.

거리 값은 상수 또는 설정값으로 분리하여 magic number가 되지 않게 해주세요.

---

# 8. 경로와 급수 스팟의 거리 계산

가능하다면 단순히

```text
현재 위치 → WaterSpot

```

거리가 아니라,

**현재 Route Polyline에서 해당 WaterSpot까지의 최소 거리**

를 계산해주세요.

예:

```text
route_distance_m = 28

```

이 값은 향후

```text
경로에서 28m

```

와 같은 UI에 사용할 예정입니다.

다만 이번 구현에서 복잡한 실제 우회 경로 계산은 하지 않아도 됩니다.

MVP에서는:

```text
Route Polyline ↔ WaterSpot

```

의 최단 직선거리를 사용해도 됩니다.

---

# 9. 급수 스팟 지도 표시

지도에서는 기존 UI 스타일에 맞는 급수 아이콘을 사용해주세요.

예:

```text
💧

```

또는 현재 프로젝트에서 사용하는 지도 아이콘 시스템에 맞는 아이콘을 사용해주세요.

급수 스팟을 선택하면 최소한 다음 정보를 표시해주세요.

```text
スポット名

💧 給水可能
ルートから約30m

```

추가 데이터가 있다면:

```text
マイボトル給水可能
利用時間 9:00〜18:00

```

등을 표시할 수 있습니다.

정보가 존재하지 않는 경우 임의의 값이나 문구를 생성하지 마세요.

---

# 10. 급수 스팟 ON/OFF

사용자가 필요할 때만 급수 스팟을 볼 수 있도록 지도 UI에 ON/OFF 기능을 추가해주세요.

예:

```text
💧 給水スポット
ON / OFF

```

기본값은 기존 UI 흐름을 고려하여 결정해주세요.

다만 토글을 OFF하면 WaterSpot marker가 지도에서 제거되어야 합니다.

Routing 결과 자체에는 영향을 주지 않습니다.

---

# 11. 선택된 Route가 변경되면 급수 스팟도 변경

여러 Route를 비교할 수 있는 경우 사용자가 선택한 Route가 변경되면 해당 Route 주변의 WaterSpot을 다시 계산해주세요.

예:

```text
最短ルート
↓
해당 Route 주변 급수소

日陰優先ルート
↓
해당 Route 주변 급수소

```

즉 현재 화면에 선택되지 않은 Route 주변의 WaterSpot까지 모두 표시하지 마세요.

---

# 12. 이번 단계에서는 급수 스팟을 Routing WayPoint로 사용하지 않기

중요합니다.

이번 구현의 목표는:

```text
Route 계산
↓
Route 주변 WaterSpot 검색
↓
지도 표시

```

까지입니다.

아직 다음 기능은 구현하지 마세요.

```text
급수소를 자동 경유하는 Route 계산

```

```text
급수소를 지나가는 경로에 가산점 부여

```

```text
10분 이상 걸으면 자동으로 급수 추천

```

```text
현재 기온에 따라 급수 알림

```

이 기능들은 실제 데이터와 UI를 검증한 후 다음 단계에서 추가할 예정입니다.

---

# 13. 테스트 — 연속 직사광선

최소한 다음 테스트를 추가해주세요.

### Case 1

```text
SHADE
SHADE
SHADE

```

결과:

```text
max_continuous_sun_m = 0

```

### Case 2

```text
SUN
SUN
SUN

```

전체 구간이 최대 연속 직사광선 거리

### Case 3

```text
SUN
SUN
SHADE
SUN

```

첫 번째 SUN 구간이 최대값

### Case 4

```text
SUN
SHADE
SUN
SUN
SUN

```

두 번째 SUN 구간이 최대값

### Case 5 — Edge 경계

```text
Edge A
SHADE
SUN
SUN

Edge B
SUN
SUN
SHADE

```

4개의 SUN sample을 하나의 연속 노출로 계산

### Case 6

```text
SUN
SHADE
SUN
SHADE
SUN

```

SHADE마다 연속 노출이 정상적으로 reset

---

# 14. 테스트 — 급수 스팟

최소한 다음 경우를 검증해주세요.

### Case 1

Route에서 50m 이내에 WaterSpot이 존재

```text
→ 검색 결과에 포함

```

### Case 2

Route에서 50m보다 멀리 WaterSpot이 존재

```text
→ 검색 결과에서 제외

```

### Case 3

여러 WaterSpot이 존재

```text
→ Route 주변의 WaterSpot만 반환

```

### Case 4

WaterSpot이 하나도 없음

```text
→ 빈 결과
→ UI 오류 없이 정상 표시

```

### Case 5

Route 변경

```text
Route A 선택
→ Route A 주변 WaterSpot 표시

Route B 선택
→ 기존 marker 갱신
→ Route B 주변 WaterSpot 표시

```

### Case 6

급수 스팟 OFF

```text
→ marker 표시하지 않음

```

---

# 15. Sampling 오차

현재 SUN/SHADE 판정에 사용하는 sampling 방식을 그대로 사용해주세요.

`max_continuous_sun_m`는 현재 sampling 해상도 기준의 근사값으로 처리하면 됩니다.

이를 정밀하게 만들기 위한 추가 Geometry 연산은 이번 단계에서는 하지 마세요.

---

# 16. 이번 작업에서 하지 않을 것

이번 작업에서는 기존 Routing Algorithm의 경로 선택 기준을 변경하지 마세요.

다음 기능은 구현 대상이 아닙니다.

```text
max_continuous_sun 값을 Routing Cost에 추가

```

```text
연속 직사광선 30초 이상 경로 제외

```

```text
WaterSpot을 경유하도록 Route 재계산

```

```text
WaterSpot이 있는 경로에 보너스 Cost 적용

```

```text
Cooling Shelter 통합

```

```text
기온/WBGT 기반 급수 알림

```

이번 단계에서는 **측정과 표시**에 집중해주세요.

---

# 17. 구현 원칙

기존 `hikage-navi`의 Architecture와 구현 방식을 그대로 유지해주세요.

- 관련 없는 코드 수정 금지
- 대규모 Refactoring 금지
- 새로운 Layer를 불필요하게 추가하지 않기
- 과도한 abstraction 금지
- 기존 sampling 로직 재사용
- 기존 OSM 처리 방식 재사용
- 기존 좌표/GIS 유틸리티 재사용
- 기존 보행 속도 값 재사용
- 새로운 라이브러리는 특별한 이유가 없는 한 추가하지 않기
- 기존 naming convention 준수
- 기존 테스트 유지
- 계산 로직과 UI 로직 분리
- 데이터가 없을 때 임의 값을 생성하지 않기

---

# 18. 작업 순서

다음 순서로 진행해주세요.

```text
1. 관련 테스트 추가

2. 최대 연속 SUN 계산 구현

3. Route/API 응답에
   max_continuous_sun_* 추가

4. Route 결과 UI 표시

5. OSM WaterSpot 데이터 처리

6. Route 주변 WaterSpot 검색

7. 지도에 WaterSpot marker 표시

8. WaterSpot ON/OFF UI 추가

9. Route 변경 시 marker 갱신

10. 전체 테스트 실행

11. 변경 내용 리뷰

```

구현이 끝나면 다음 내용을 간략하게 정리해주세요.

- 변경한 파일
- `max_continuous_sun` 계산 방식
- WaterSpot 데이터 취득 및 필터링 방식
- Route와 WaterSpot 거리 계산 방식
- 추가한 테스트
- 테스트 결과
- 구현 과정에서 발견된 데이터 품질 문제
- 향후 Routing에 `Max Continuous Exposure Constraint`를 적용할 경우 수정할 부분
- 향후 `급수소 경유 Route`를 구현할 경우 수정할 부분
