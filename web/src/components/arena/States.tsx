import type { ReactNode } from "react";
import { COPY } from "../../lib/constants";

/**
 * First-fetch loading state: the card layout with --surface-1 blocks where
 * text goes and all pips in --model-off. No spinner, no shimmer.
 */
export function LoadingBlocks({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="loading-blocks" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="loading-card cut-l">
          <div className="loading-line loading-line-wide" />
          <div className="loading-line loading-line-narrow" />
          <div className="pipbar-track" aria-hidden="true">
            {Array.from({ length: 20 }, (_, j) => <span key={j} className="pipbar-block" />)}
          </div>
        </div>
      ))}
    </div>
  );
}

/** fails /api/snapshot: fixed copy, optional last-good time, optional Retry. Cached cards stay visible below it (caller's job). */
export function ErrorPanel({ lastGood, detail, onRetry }: { lastGood?: string; detail?: string; onRetry?: () => void }) {
  return (
    <div className="error-panel cut-l">
      <div className="error-panel-title">{COPY.couldntReach}</div>
      {lastGood && <p className="error-panel-line">Last good data: {lastGood}.</p>}
      {detail && <p className="error-panel-detail num">{detail}</p>}
      {onRetry && <button type="button" className="btn btn-secondary" onClick={onRetry}>Retry</button>}
    </div>
  );
}

/** No upcoming matches for the current filter, or any other "nothing here" case. */
export function EmptyState({ title, line, action }: { title: string; line: string; action?: ReactNode }) {
  return (
    <div className="empty-state cut-l">
      <div className="empty-state-title">{title}</div>
      <p className="empty-state-line">{line}</p>
      {action}
    </div>
  );
}

/** Payload older than STALE_HOURS: one meta line under the header. `asOf` is caller-formatted. */
export function StaleNote({ asOf }: { asOf: string }) {
  return <p className="stale-note num">Forecasts from {asOf}. The data desk has not updated since.</p>;
}
