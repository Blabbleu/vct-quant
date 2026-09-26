import type { ReactNode } from "react";

export type ChipVariant = "default" | "model" | "market" | "result" | "ghost";

/** Slanted chip/tag used throughout (LOW DATA, UPSET, WIN, status). */
export function Chip({ variant = "default", children }: { variant?: ChipVariant; children: ReactNode }) {
  return (
    <span className={`chip-arena slant chip-arena-${variant}`}>
      <span>{children}</span>
    </span>
  );
}

/** T-14H / T-3D countdown to kick-off, or LIVE once start has passed. */
export function CountdownChip({ iso }: { iso: string }) {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) {
    return (
      <Chip variant="market">
        <span className="live-dot" aria-hidden="true" />LIVE
      </Chip>
    );
  }
  const hours = diffMs / 3_600_000;
  const label = hours < 48 ? `T\u2212${Math.max(1, Math.ceil(hours))}H` : `T\u2212${Math.ceil(hours / 24)}D`;
  return <Chip variant="default"><span className="num">{label}</span></Chip>;
}
