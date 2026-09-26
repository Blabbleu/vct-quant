import type { ReactNode } from "react";

export type StatTone = "model" | "market" | "result";

/** A single cut-corner stat cell: mono value + label underneath (MODEL, MARKET, CALL...). */
export default function StatCell({ label, value, tone }: {
  label: string; value: ReactNode; tone?: StatTone;
}) {
  return (
    <div className={`statcell cut-m${tone ? ` statcell-${tone}` : ""}`}>
      <div className="statcell-value num">{value}</div>
      <div className="statcell-label">{label}</div>
    </div>
  );
}
