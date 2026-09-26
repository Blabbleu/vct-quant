import type { CalibrationBucket } from "../lib/types";

/**
 * Hand-written SVG calibration plot: predicted vs actual win rate per bucket.
 * A dashed --line diagonal is the reference (perfectly calibrated); model
 * points/segments are chartreuse, sized by bucket n. Mono axis labels, at
 * most three per axis, no legend box.
 */
export default function Calibration({ buckets }: { buckets: CalibrationBucket[] }) {
  const S = 300, P = 34;
  const s = (v: number) => P + v * (S - 2 * P);
  const usable = buckets.filter(b => b.n > 0);
  const max = Math.max(...usable.map(b => b.n), 1);
  const sorted = [...usable].sort((a, b) => a.predicted - b.predicted);
  const path = sorted.map((b, i) => `${i === 0 ? "M" : "L"} ${s(b.predicted)} ${S - s(b.actual)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="chart square" role="img" aria-label="Calibration plot: predicted vs actual win rate">
      {[0, 0.5, 1].map(g => (
        <g key={g}>
          <line x1={s(0)} x2={s(1)} y1={S - s(g)} y2={S - s(g)} className="grid" />
          <text x={s(0) - 6} y={S - s(g) + 4} className="axis" textAnchor="end">{g * 100}%</text>
          <text x={s(g)} y={S - P + 18} className="axis" textAnchor="middle">{g * 100}%</text>
        </g>
      ))}
      {/* Diagonal reference: perfectly calibrated. */}
      <line x1={s(0)} y1={S - s(0)} x2={s(1)} y2={S - s(1)} className="grid mid dashed" />
      {sorted.length > 1 && <path d={path} className="line elo" fill="none" />}
      {usable.map(b => (
        <circle key={b.predicted} cx={s(b.predicted)} cy={S - s(b.actual)}
          r={3 + 9 * Math.sqrt(b.n / max)} className="pt elo soft">
          <title>{`predicted ${(b.predicted * 100).toFixed(0)}% \u2192 actual ${(b.actual * 100).toFixed(0)}% (n=${b.n})`}</title>
        </circle>
      ))}
    </svg>
  );
}
