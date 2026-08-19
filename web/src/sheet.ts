import { copy } from "./copy";
import { formatPath } from "./api";
import type { AppState, PathDto, Phase } from "./types";

export type SheetSnap = "peek" | "half" | "expanded";

export function selectedPath(state: AppState): PathDto | null {
  const route = state.route;
  if (!route) return null;
  if (state.selected === "shadiest" && route.shadiest) return route.shadiest;
  return route.shortest;
}

export function peekHeadline(state: AppState, loading: boolean): string {
  if (loading) return copy.loadingRoute;
  switch (state.phase) {
    case "S0":
      return copy.s0;
    case "S1":
      return copy.peekS1;
    case "S2":
      return copy.search;
    case "S3": {
      const path = selectedPath(state);
      if (!path) return copy.s0;
      const label =
        state.selected === "shadiest" && state.route?.shadiest
          ? copy.legendShade
          : copy.legendShortest;
      return `${label} ${formatPath(path)}`;
    }
    case "S4": {
      const p = state.route?.shortest;
      if (!p) return copy.nightOnly;
      return `${copy.nightBadge} · ${copy.legendShortest} ${p.distance_m}m · ${p.duration_min}分`;
    }
    case "S5":
      return state.errorMessage ?? "";
    default:
      return copy.s0;
  }
}

export function advanceSheetSnap(snap: SheetSnap): SheetSnap {
  if (snap === "peek") return "half";
  if (snap === "half") return "expanded";
  return "peek";
}

export function sheetAfterMapTap(): SheetSnap {
  return "peek";
}

export function sheetHeightVar(snap: SheetSnap): string {
  if (snap === "peek") return "var(--sheet-peek)";
  if (snap === "half") return "var(--sheet-half)";
  return "var(--sheet-expanded)";
}

export function clampShadePct(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, Math.round(n)));
}

export function showPeekSearch(
  phase: Phase,
  loading: boolean,
  snap: SheetSnap,
): boolean {
  return phase === "S2" && !loading && snap === "peek";
}
