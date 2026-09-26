import type { ReactNode } from "react";

/**
 * Bordered cut-corner panel: two nested clipped layers (the spec's "a
 * bordered panel is two nested clipped layers"). The outer layer carries
 * --line (or --result for a winner frame) with 1-2px of padding; the inner
 * surface is clipped the same way so the border reads as a hairline even on
 * the cut corners. `brackets` adds the four 12px corner L-shapes used on the
 * one panel per page that matters most (the model-vs-market gap panel).
 */
export default function Panel({ cut, frame = "line", brackets = false, className, children }: {
  cut: "l" | "m"; frame?: "line" | "result" | "none"; brackets?: boolean; className?: string; children: ReactNode;
}) {
  const cutClass = cut === "l" ? "cut-l" : "cut-m";
  const frameClass = frame === "result" ? "frame-result" : frame === "none" ? "frame-none" : "";
  return (
    <div className={`panel-arena-wrap${className ? ` ${className}` : ""}`}>
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
    </div>
  );
}
