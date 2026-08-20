import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "styles.css"), "utf8");
const html = readFileSync(resolve(__dirname, "../index.html"), "utf8");

describe("mobile layout regression", () => {
  it("uses viewport-fit=cover", () => {
    expect(html).toContain("viewport-fit=cover");
  });

  it("sets theme-color for mobile browser chrome", () => {
    expect(html).toMatch(/name="theme-color"/);
  });

  it("applies safe-area insets to chrome and sheet", () => {
    expect(css).toMatch(/env\(safe-area-inset-top/);
    expect(css).toMatch(/env\(safe-area-inset-bottom/);
  });

  it("keeps touch targets at least 44px", () => {
    expect(css).toMatch(/button\s*\{[^}]*min-height:\s*44px/s);
    expect(css).toMatch(/\.datetime input[^}]*min-height:\s*44px/s);
  });

  it("limits peek sheet to 40% of viewport height", () => {
    expect(css).toMatch(/--sheet-peek:[^;]*40dvh/s);
  });

  it("wraps top bar on narrow screens", () => {
    expect(css).toMatch(/@media \(max-width: 899px\)[\s\S]*\.topbar[\s\S]*flex-wrap:\s*wrap/s);
  });

  it("uses 16px datetime input to avoid iOS zoom", () => {
    expect(css).toMatch(/\.datetime input[^}]*font-size:\s*16px/s);
  });

  it("guards map height in landscape", () => {
    expect(css).toMatch(
      /@media \(max-height: 500px\) and \(orientation: landscape\)/,
    );
    expect(css).toMatch(/\.map-wrap[^}]*min-height:\s*140px/s);
  });

  it("positions location FAB above each sheet snap", () => {
    expect(css).toMatch(/\.snap-peek \.location-fab/);
    expect(css).toMatch(/\.snap-half \.location-fab/);
    expect(css).toMatch(/\.snap-expanded \.location-fab/);
  });
});
