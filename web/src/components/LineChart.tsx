import type { MovementPoint } from "../lib/types";

/** Model and market over time for team A. Plain SVG, no chart dependency. */
export default function LineChart({ points }: { points: MovementPoint[] }) {
  const W = 640, H = 240, L = 36, R = 12, T = 12, B = 28;
  const ts = points.map(p => new Date(p.observed_at).getTime());
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const x = (t: number) => (t1 === t0 ? L + (W - L - R) / 2 : L + ((t - t0) / (t1 - t0)) * (W - L - R));
  const y = (p: number) => T + (1 - p) * (H - T - B);
  const path = (vals: (number | null)[]) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(ts[i]).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const fmt = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Win probability over time">
      {[0, 0.25, 0.5, 0.75, 1].map(g => (
        <g key={g}>
          <line x1={L} x2={W - R} y1={y(g)} y2={y(g)} className={g === 0.5 ? "grid mid" : "grid"} />
          <text x={L - 6} y={y(g) + 4} className="axis" textAnchor="end">{g * 100}%</text>
        </g>
      ))}
      <text x={L} y={H - 8} className="axis">{fmt(t0)}</text>
      <text x={W - R} y={H - 8} className="axis" textAnchor="end">{fmt(t1)}</text>
      <path d={path(points.map(p => p.market))} className="line mkt" />
      <path d={path(points.map(p => p.elo))} className="line elo" />
      {points.map((p, i) => (
        <g key={p.observed_at}>
          {p.market != null && <circle cx={x(ts[i])} cy={y(p.market)} r={3} className="pt mkt" />}
          <circle cx={x(ts[i])} cy={y(p.elo)} r={3} className="pt elo" />
        </g>
      ))}
    </svg>
  );
}
