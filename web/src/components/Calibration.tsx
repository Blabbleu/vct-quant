import type { CalibrationBucket } from "../lib/types";

export default function Calibration({ buckets }: { buckets: CalibrationBucket[] }) {
  const S = 300, P = 34;
  const s = (v: number) => P + v * (S - 2 * P);
  const max = Math.max(...buckets.map(b => b.n), 1);
  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="chart square" role="img" aria-label="Calibration plot">
      {[0, 0.5, 1].map(g => (
        <g key={g}>
          <line x1={s(0)} x2={s(1)} y1={S - s(g)} y2={S - s(g)} className="grid" />
          <text x={s(0) - 6} y={S - s(g) + 4} className="axis" textAnchor="end">{g * 100}%</text>
          <text x={s(g)} y={S - P + 18} className="axis" textAnchor="middle">{g * 100}%</text>
        </g>
      ))}
      <line x1={s(0)} y1={S - s(0)} x2={s(1)} y2={S - s(1)} className="grid mid dashed" />
      {buckets.map(b => (
        <circle key={b.predicted} cx={s(b.predicted)} cy={S - s(b.actual)}
          r={3 + 9 * Math.sqrt(b.n / max)} className="pt elo soft">
          <title>{`predicted ${(b.predicted * 100).toFixed(0)}% → actual ${(b.actual * 100).toFixed(0)}% (n=${b.n})`}</title>
        </circle>
      ))}
    </svg>
  );
}
