/**
 * 20 rectangular blocks (10 on outcome tiles), each a fixed share of team A's win
 * chance. Filled blocks are --model, the rest --model-off. A gold triangle
 * notch floats above the bar at the market's exact percentage (not rounded
 * to a block); it is omitted with no market. `lowData` renders outline
 * blocks instead of filled ones (see the Low data state in the spec).
 */
export default function PipBar({ pA, market, blocks = 20, lowData = false }: {
  pA: number; market?: number | null; blocks?: number; lowData?: boolean;
}) {
  const filled = Math.round(Math.max(0, Math.min(1, pA)) * blocks);
  const label = `Model ${(pA * 100).toFixed(1)}%` + (market != null ? `, market ${(market * 100).toFixed(1)}%` : "");
  return (
    <div className="pipbar" role="img" aria-label={label}>
      {market != null && (
        <div className="pipbar-notch" style={{ left: `${Math.max(0, Math.min(100, market * 100))}%` }} aria-hidden="true" />
      )}
      <div className="pipbar-track">
        {Array.from({ length: blocks }, (_, i) => (
          <span
            key={i}
            className={`pipbar-block${i < filled ? " pipbar-block-filled" : ""}${lowData ? " pipbar-block-outline" : ""}`}
          />
        ))}
      </div>
    </div>
  );
}
