# 지도 위 유리 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 지도를 전체 화면으로 두고 유리 알약·바텀 시트로 S0–S5를 한손 조작할 수 있게 한다.

**Architecture:** 상태 기계는 `reduce`에 그대로 둔다. 시트 스냅·peek 문구·그늘% 클램프만 `sheet.ts` 순수 함수로 뺀다. 크롬은 CSS overlay. 링은 `ShadeRing`(conic-gradient). 시트 높이만 `animejs`.

**Tech Stack:** React 18, Vite, 기존 CSS, animejs, Vitest. Tailwind/shadcn/Bklit 패키지 없음.

**Spec:** `docs/superpowers/specs/2026-08-19-map-glass-ui-design.md`

## Global Constraints

- API·S0–S5·일본어 확정 문안(`copy.ts` 기존 키)을 바꾸지 않는다. peek 전용은 `peekS1`만 추가.
- 급수는 지도 마커 + 범례 토글만. 시트 목록 없음.
- 링은 그늘 % 하나. 야간(S4)에는 링을 그리지 않는다.
- `prefers-reduced-motion: reduce`이면 anime를 돌리지 않는다.
- 웹 테스트: `cd web && npm test`

---

### Task 1: 시트 순수 함수

**Files:**
- Create: `web/src/sheet.ts`
- Create: `web/src/sheet.test.ts`
- Modify: `web/src/copy.ts` (`peekS1` 추가)

**Interfaces:**
- Consumes: `AppState`, `copy`, `formatPath`
- Produces:
  - `export type SheetSnap = "peek" | "half" | "expanded"`
  - `export function selectedPath(state: AppState): PathDto | null`
  - `export function peekHeadline(state: AppState, loading: boolean): string`
  - `export function advanceSheetSnap(snap: SheetSnap): SheetSnap`
  - `export function sheetAfterMapTap(): "peek"`
  - `export function clampShadePct(n: number): number`

- [ ] **Step 1: Write the failing test**

`web/src/sheet.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { copy } from "./copy";
import { formatPath } from "./api";
import {
  advanceSheetSnap,
  clampShadePct,
  peekHeadline,
  selectedPath,
  sheetAfterMapTap,
} from "./sheet";
import { initialState, reduce } from "./state";
import type { PathDto, RouteResponse } from "./types";

const origin = { lon: 139.7016, lat: 35.658, inBoundary: true };
const dest = { lon: 139.7027, lat: 35.657, inBoundary: true };

function path(over: Partial<PathDto> = {}): PathDto {
  return {
    coordinates: [],
    distance_m: 315,
    duration_min: 4,
    shade_m: 120,
    sun_m: 195,
    shade_pct: 80,
    max_continuous_sun_m: 24,
    max_continuous_sun_seconds: 18,
    water_spots: [],
    ...over,
  };
}

function dayRoute(): RouteResponse {
  return {
    night: false,
    same_route: false,
    long_detour: false,
    warning: null,
    shortest: path({ shade_pct: 39, distance_m: 315 }),
    shadiest: path({ shade_pct: 80, distance_m: 316 }),
  };
}

describe("peekHeadline", () => {
  it("shows loading over any phase", () => {
    expect(peekHeadline(initialState(), true)).toBe(copy.loadingRoute);
  });

  it("S0 uses s0", () => {
    expect(peekHeadline(initialState(), false)).toBe(copy.s0);
  });

  it("S1 uses peekS1", () => {
    const s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    expect(peekHeadline(s, false)).toBe(copy.peekS1);
  });

  it("S3 uses selected path label and formatPath", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    s = reduce(s, { type: "ROUTE_OK", route: dayRoute() });
    expect(s.selected).toBe("shadiest");
    expect(peekHeadline(s, false)).toBe(
      `${copy.legendShade} ${formatPath(dayRoute().shadiest!)}`,
    );
  });

  it("S4 is night shortest without shade pct", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    const night = {
      ...dayRoute(),
      night: true,
      shadiest: null,
      shortest: path({ distance_m: 315, duration_min: 4 }),
    };
    s = reduce(s, { type: "ROUTE_OK", route: night });
    expect(peekHeadline(s, false)).toBe("夜間 · 最短 315m · 4分");
  });
});

describe("selectedPath", () => {
  it("returns shadiest when selected", () => {
    let s = reduce(initialState(), { type: "MAP_TAP", point: origin });
    s = reduce(s, { type: "MAP_TAP", point: dest });
    s = reduce(s, { type: "ROUTE_OK", route: dayRoute() });
    expect(selectedPath(s)?.shade_pct).toBe(80);
  });
});

describe("sheet snap", () => {
  it("cycles peek → half → expanded → peek", () => {
    expect(advanceSheetSnap("peek")).toBe("half");
    expect(advanceSheetSnap("half")).toBe("expanded");
    expect(advanceSheetSnap("expanded")).toBe("peek");
  });

  it("map tap collapses to peek", () => {
    expect(sheetAfterMapTap()).toBe("peek");
  });
});

describe("clampShadePct", () => {
  it("clamps to 0–100 integers", () => {
    expect(clampShadePct(-3)).toBe(0);
    expect(clampShadePct(80.4)).toBe(80);
    expect(clampShadePct(150)).toBe(100);
    expect(clampShadePct(Number.NaN)).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/sheet.test.ts`
Expected: FAIL — `sheet.ts` 없음 또는 `peekS1` 없음.

- [ ] **Step 3: Write minimal implementation**

`copy.ts`에 `peekS1: "次に到着地点をタップしてください"`.

`sheet.ts`에 위 시그니처 구현. S5는 `state.errorMessage ?? ""`. S2 peek 문자열은 `copy.search` (버튼 라벨과 동일; UI는 버튼으로 그림).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/sheet.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/sheet.ts web/src/sheet.test.ts web/src/copy.ts
git commit -m "feat: 유리 시트 peek 문구와 스냅을 순수 함수로 둔다"
```

---

### Task 2: ShadeRing

**Files:**
- Create: `web/src/ShadeRing.tsx`
- Modify: `web/src/sheet.test.ts` — `clampShadePct`는 Task 1. 이 태스크는 링이 `clampShadePct`를 쓰도록 컴포넌트만.

**Interfaces:**
- Consumes: `clampShadePct`, `--short` / `--shade`
- Produces: `export function ShadeRing(props: { pct: number; tone: "short" | "shade" }): JSX.Element`

- [ ] **Step 1–4:** 컴포넌트는 시각이라 단위 테스트는 `clampShadePct`에 위임. `ShadeRing`은 `role="img"` `aria-label={`${pct}%`}` 인 conic-gradient `div.shade-ring`.

- [ ] **Step 5: Commit** with `ShadeRing.tsx` after Task 3 if wired in the same commit as layout — prefer implement ring CSS in Task 3 commit together if smaller. **Do not skip the ring.** Include in Task 3 files if needed to avoid an empty test task.

---

### Task 3: Overlay 레이아웃 + 시트 UI

**Files:**
- Modify: `web/index.html` — `viewport-fit=cover`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.tsx` — `.app` overlay, `sheetSnap` state, map tap → peek
- Modify: `web/src/TopBar.tsx` — `.topbar` 알약
- Modify: `web/src/Panel.tsx` — 시트 + FAB로 現在地 분리 (`LocationFab`는 Panel에서 렌더하거나 App에서)
- Modify: `web/src/MapView.tsx` — 범례를 알약 아래 유리 칩
- Modify: `docs/03-ui-spec.md` §1 레이아웃 메모
- Create: `web/src/ShadeRing.tsx`

**Interfaces:**
- Consumes: Task 1 함수, 기존 Panel 핸들러
- Produces: 지도 full-bleed, 유리 시트, FAB

- [ ] **Step 1:** `index.html` viewport `viewport-fit=cover`
- [ ] **Step 2:** `.app`를 `position: relative; height: 100dvh`. `.map-wrap { position:absolute; inset:0 }`. `.topbar` / `.legend` / `.panel` / `.location-fab` `position:absolute; z-index`. 데스크톱 `@media (min-width: 900px)`에서 `.panel`을 `left: 12px; top: 72px; bottom: 12px; width: 340px` 레일로.
- [ ] **Step 3:** Panel: 핸들 탭 → `advanceSheetSnap`. peek S2는 探す 버튼. 카드에 `ShadeRing`. 現在地는 `.location-fab`.
- [ ] **Step 4:** `cd web && npm test` 전부 PASS. `npx tsc --noEmit` PASS.
- [ ] **Step 5: Commit**

```
feat: 지도를 전체 화면으로 두고 유리 시트와 알약을 얹는다
```

---

### Task 4: anime.js 시트 높이

**Files:**
- Modify: `web/package.json` — `animejs`
- Modify: `web/src/Panel.tsx` 또는 `web/src/sheetMotion.ts`

**Interfaces:**
- Consumes: `SheetSnap`, `window.matchMedia("(prefers-reduced-motion: reduce)")`
- Produces: snap 변경 시 높이 애니메이션 220ms. reduce면 즉시.

- [ ] **Step 1:** `cd web && npm install animejs && npm install -D @types/animejs` — animejs 4는 자체 타입일 수 있음. 설치 후 `import { animate } from "animejs"`가 되면 `@types`는 넣지 않는다.
- [ ] **Step 2:** snap별 높이: peek `calc(88px + env(safe-area-inset-bottom))`, half `min(38vh, 320px)`, expanded `min(52vh, 480px)`.
- [ ] **Step 3:** `cd web && npm test`
- [ ] **Step 4: Commit**

```
feat: 시트 스냅 높이를 anime.js로 보간한다
```

---

## Spec coverage

| Spec | Task |
| --- | --- |
| peek 문구·스냅 | 1 |
| ShadeRing | 3 |
| overlay 레이아웃·FAB·알약 | 3 |
| 03-ui-spec · viewport | 3 |
| anime.js · reduced motion | 4 |
| 급수 시트 목록 금지 | 3 (기존 범례 유지) |
