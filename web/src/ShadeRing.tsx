import { clampShadePct } from "./sheet";

type Props = { pct: number; tone: "short" | "shade" };

export function ShadeRing({ pct, tone }: Props) {
  const n = clampShadePct(pct);
  const color = `var(--${tone === "short" ? "short" : "shade"})`;
  return (
    <div
      className={`shade-ring shade-ring-${tone}`}
      role="img"
      aria-label={`${n}%`}
      style={{
        background: `conic-gradient(${color} ${n * 3.6}deg, var(--line) 0)`,
      }}
    >
      <span className="shade-ring-hole">{n}</span>
    </div>
  );
}
