import type { ReactNode } from "react";

export function Loading({ what = "forecasts" }: { what?: string }) {
  return <p className="muted pad">Loading {what}…</p>;
}

export function Failure({ error }: { error: string }) {
  return (
    <div className="panel pad">
      <b>Could not load data.</b>
      <p className="muted">{error}</p>
    </div>
  );
}

export function PageHead({ eyebrow, title, children }: { eyebrow?: string; title: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      <h1>{title}</h1>
      {children && <p className="lede">{children}</p>}
    </header>
  );
}

export function Tile({ value, label, hero = false }: { value: ReactNode; label: ReactNode; hero?: boolean }) {
  return (
    <div className={hero ? "tile hero" : "tile"}>
      <span className="v">{value}</span>
      <span className="k">{label}</span>
    </div>
  );
}

/** Two-sided probability bar: team A share on the left in the Elo colour. */
export function SplitBar({ p }: { p: number }) {
  const a = Math.round(p * 1000) / 10;
  return (
    <div className="split-bar" role="img" aria-label={`${a}% vs ${(100 - a).toFixed(1)}%`}>
      <i className="a" style={{ width: `${a}%` }} />
      <i className="b" style={{ width: `${100 - a}%` }} />
    </div>
  );
}
