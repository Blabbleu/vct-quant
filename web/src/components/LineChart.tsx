import type { MovementPoint } from "../lib/types";
import { spreadLabels } from "../lib/matchView";

/**
 * Model vs market over time for team A. Hand-written SVG, spec "Chart"
 * style: every line is stepped (each forecast holds until the next is
 * logged), hairline --surface-2 grid with a dashed 50% mid-line, a dashed
 * --result START marker at the first point, end markers shaped like the
 * series (model = slanted square, market = triangle), mono axis labels
 * (<=3 per axis) and no legend box -- the lines are labelled directly at
 * their ends. Colours come from the shared .chart / .line / .pt rules in
 * styles.css; only the START marker and end labels need explicit fills
 * since those aren't covered by the shared elo/mkt class pair.
 */
export default function LineChart({ points, teamLabel = "team A" }: { points: MovementPoint[]; teamLabel?: string }) {
  const W = 640, H = 256, L = 40, R = 64, T = 30, B = 32;
  const ts = points.map(p => new Date(p.observed_at).getTime());
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const xEnd = W - R;
  const x = (t: number) => (t1 === t0 ? L + (xEnd - L) / 2 : L + ((t - t0) / (t1 - t0)) * (xEnd - L));
  const y = (p: number) => T + (1 - p) * (H - T - B);

  function stepPath(vals: (number | null)[]): { d: string; endX: number; endY: number } | null {
    let d = "", started = false, lastX = 0, lastY = 0;
    vals.forEach((v, i) => {
      if (v == null) { started = false; return; }
      const px = x(ts[i]), py = y(v);
      if (!started) { d += `M${px.toFixed(1)},${py.toFixed(1)}`; started = true; }
      else { d += `L${px.toFixed(1)},${lastY.toFixed(1)}L${px.toFixed(1)},${py.toFixed(1)}`; }
      lastX = px; lastY = py;
    });
    if (!d) return null;
    if (lastX < xEnd) d += `L${xEnd.toFixed(1)},${lastY.toFixed(1)}`;
    return { d, endX: xEnd, endY: lastY };
  }

  const modelPath = stepPath(points.map(p => p.elo));
  const marketVals = points.map(p => p.market);
  const hasMarket = marketVals.some(v => v != null);
  const marketPath = hasMarket ? stepPath(marketVals) : null;

  const fmt = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const startX = x(ts[0]);

  return (
    <div className="chart-box">
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Chance of ${teamLabel} winning, over time`}>
      {[0, 0.5, 1].map(g => (
        <g key={g}>
          <line x1={L} x2={xEnd} y1={y(g)} y2={y(g)} className={g === 0.5 ? "grid mid" : "grid"} />
          <text x={L - 6} y={y(g) + 4} className="axis" textAnchor="end">{g * 100}%</text>
        </g>
      ))}
      {/* Dashed --result START marker at the first logged point. The label sits above the plot, to the right of the
          marker, so it can never meet the y-axis labels. */}
      <line x1={startX} x2={startX} y1={T - 6} y2={H - B} className="dashed" style={{ stroke: "var(--result)" }} />
      <text x={startX + 5} y={T - 12} className="axis" textAnchor="start" style={{ fill: "var(--result)" }}>START</text>

      {marketPath && <path d={marketPath.d} className="line mkt" />}
      {modelPath && <path d={modelPath.d} className="line elo" />}

      {/* End markers, shaped like the series: model = slanted square, market = triangle. */}
      {modelPath && (
        <rect x={modelPath.endX - 4} y={modelPath.endY - 4} width={8} height={8}
          className="pt elo" transform={`rotate(-14 ${modelPath.endX} ${modelPath.endY})`} />
      )}
      {marketPath && (
        <polygon
          points={`${marketPath.endX},${marketPath.endY - 5} ${marketPath.endX + 5},${marketPath.endY + 4} ${marketPath.endX - 5},${marketPath.endY + 4}`}
          className="pt mkt"
        />
      )}

      {/* Label the ends directly, in the right margin beside each end marker; spread so labels never overlap. */}
      {(() => {
        const items = [
          modelPath && { text: "MODEL", fill: "var(--model)", y: modelPath.endY + 4, x: modelPath.endX + 12 },
          marketPath && { text: "MARKET", fill: "var(--market)", y: marketPath.endY + 4, x: marketPath.endX + 12 },
        ].filter((v): v is { text: string; fill: string; y: number; x: number } => !!v);
        const ys = spreadLabels(items.map(i => i.y), 15, T + 4, H - B - 2);
        return items.map((it, k) => <text key={it.text} x={it.x} y={ys[k]} className="axis" textAnchor="start" style={{ fill: it.fill }}>{it.text}</text>);
      })()}

      <text x={L} y={H - 10} className="axis">{fmt(t0)}</text>
      <text x={xEnd} y={H - 10} className="axis" textAnchor="end">{fmt(t1)}</text>
    </svg>
    </div>
  );
}
