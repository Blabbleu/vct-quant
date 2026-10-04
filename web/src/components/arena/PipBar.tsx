import { m, useInitial, EASE_OUT, D_BASE } from "../../lib/motion";

/**
 * 20 rectangular blocks (10 on outcome tiles), each a fixed share of team A's win
 * chance. Filled blocks are --model, the rest --model-off. A gold triangle
 * notch floats above the bar at the market's exact percentage (not rounded
 * to a block); it is omitted with no market. `lowData` renders outline
 * blocks instead of filled ones (see the Low data state in the spec).
 *
 * Motion: the filled blocks sweep in left to right (scaleX 0 -> 1, staggered) the first
 * time the bar scrolls into view; the notch fades in after the sweep. Reduced motion
 * renders the final bar at once.
 */
export default function PipBar({ pA, market, blocks = 20, lowData = false }: {
  pA: number; market?: number | null; blocks?: number; lowData?: boolean;
}) {
  const filled = Math.round(Math.max(0, Math.min(1, pA)) * blocks);
  const label = `Model ${(pA * 100).toFixed(1)}%` + (market != null ? `, market ${(market * 100).toFixed(1)}%` : "");
  const init = useInitial("hidden");
  const step = blocks > 12 ? 0.014 : 0.02;
  return (
    <m.div
      className="pipbar" role="img" aria-label={label}
      initial={init} whileInView="show" viewport={{ once: true, amount: 0.3 }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: step, delayChildren: 0.05 } } }}
    >
      {market != null && (
        <m.div
          className="pipbar-notch" style={{ left: `${Math.max(0, Math.min(100, market * 100))}%` }} aria-hidden="true"
          variants={{ hidden: { opacity: 0 }, show: { opacity: 1, transition: { delay: filled * step + 0.15, duration: D_BASE, ease: EASE_OUT } } }}
        />
      )}
      <div className="pipbar-track">
        {Array.from({ length: blocks }, (_, i) => i < filled ? (
          <m.span
            key={i}
            className={`pipbar-block pipbar-block-filled${lowData ? " pipbar-block-outline" : ""}`}
            style={{ originX: 0 }}
            variants={{ hidden: { scaleX: 0, opacity: 0 }, show: { scaleX: 1, opacity: 1, transition: { duration: D_BASE, ease: EASE_OUT } } }}
          />
        ) : (
          <span key={i} className={`pipbar-block${lowData ? " pipbar-block-outline" : ""}`} />
        ))}
      </div>
    </m.div>
  );
}
