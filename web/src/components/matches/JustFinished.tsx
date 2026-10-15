import { Link } from "react-router-dom";
import FinishedCard from "./FinishedCard";
import SectionHead from "../arena/SectionHead";
import type { Async } from "./RailPanels";
import type { ResultsList } from "../../lib/types";
import { justFinished } from "../../lib/matchesData";
import { Stagger, StaggerItem } from "../../lib/motion";

/** Recent verified matches, bounded by the current 48-hour window. */
export default function JustFinished({ results }: { results: Async<ResultsList> }) {
  const rows = results.data ? justFinished(results.data.rows) : [];
  const hasVerified = results.data?.rows.some(r => r.result.status === "verified" && r.result.winner != null) ?? false;

  return (
    <section className="matches-day matches-finished">
      <SectionHead title="Just finished" right={<Link to="/results" className="num small">All results &rarr;</Link>} />
      {results.loading ? (
        <div className="matches-board" aria-busy="true" aria-label="Loading results">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="loading-card cut-l"><div className="loading-line loading-line-wide" /><div className="loading-line loading-line-narrow" /></div>
          ))}
        </div>
      ) : results.error ? (
        <p className="muted small">Results unavailable right now ({results.error}).</p>
      ) : rows.length === 0 ? (
        <p className="muted small">{hasVerified ? "No recent graded matches." : "No graded matches yet."}</p>
      ) : (
        <Stagger className="matches-board">
          {rows.map(r => <StaggerItem key={r.match_id} className="stagger-cell"><FinishedCard r={r} /></StaggerItem>)}
        </Stagger>
      )}
    </section>
  );
}
