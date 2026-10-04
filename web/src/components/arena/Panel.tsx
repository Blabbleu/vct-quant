import type { ReactNode } from "react";

/**
 * Bordered panel: two nested layers, a --line frame with 1-2px of padding around
 * a surface, both 4px-rounded (the cut-corner shapes are retired). `brackets` is
 * kept for call-site compatibility; the corner marks are hidden by CSS.
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
