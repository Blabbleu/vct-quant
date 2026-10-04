import type { ReactNode } from "react";
import { m, useCanHover, D_FAST } from "../../lib/motion";

/**
 * Bordered cut-corner panel: two nested clipped layers, a --line frame with 1-2px of
 * padding around a surface, both clipped the same way so the border reads as a hairline
 * even on the cut corners. `brackets` adds the four 12px --model corner L-shapes.
 * `lift` raises the panel 2px on hover (pointer devices) and presses it in on tap;
 * only transform animates, the border/fill change is CSS.
 */
export default function Panel({ cut, frame = "line", brackets = false, lift = false, className, children }: {
  cut: "l" | "m"; frame?: "line" | "result" | "none"; brackets?: boolean; lift?: boolean; className?: string; children: ReactNode;
}) {
  const cutClass = cut === "l" ? "cut-l" : "cut-m";
  const frameClass = frame === "result" ? "frame-result" : frame === "none" ? "frame-none" : "";
  const canHover = useCanHover();
  return (
    <m.div
      className={`panel-arena-wrap${className ? ` ${className}` : ""}`}
      whileHover={lift && canHover ? { y: -2, transition: { duration: D_FAST } } : undefined}
      whileTap={lift ? { scale: 0.985, transition: { duration: 0.1 } } : undefined}
    >
      <div className={`arena-frame ${frameClass} ${cutClass}`}>
        <div className={`arena-surface ${cutClass}`}>{children}</div>
      </div>
      {brackets && (
        <>
          <span className="panel-bracket panel-bracket-tl" aria-hidden="true" />
          <span className="panel-bracket panel-bracket-tr" aria-hidden="true" />
          <span className="panel-bracket panel-bracket-bl" aria-hidden="true" />
          <span className="panel-bracket panel-bracket-br" aria-hidden="true" />
        </>
      )}
    </m.div>
  );
}
