import type { ResultMap } from "../../lib/types";
import "./MapStrip.css";

/**
 * Map-by-map strip for a finished series: one cut-corner cell per map with
 * the map name and each side's round score, the winner's rounds in
 * --result. When round scores are not stored (`maps.length === 0`) it renders nothing.
 */
export default function MapStrip({
  maps, teamA, teamB,
}: {
  maps: ResultMap[]; teamA: string; teamB: string;
}) {
  // No stored round scores: render nothing (the honest note lives in ResultPanel) rather than placeholder cells.
  if (maps.length === 0) return null;
  return (
    <div className="mapstrip" role="img" aria-label={`Map scores, ${teamA} vs ${teamB}`}>
      {maps.map(m => {
        const aWon = m.rounds_a > m.rounds_b;
        return (
          <div className="mapstrip-cell cut-m" key={m.number}>
            <span className="mapstrip-num num">M{m.number}</span>
            <span className="mapstrip-map">{m.map}</span>
            <span className="mapstrip-score num">
              <span className={aWon ? "mapstrip-win" : "mapstrip-lose"}>{m.rounds_a}</span>
              {"\u2013"}
              <span className={!aWon ? "mapstrip-win" : "mapstrip-lose"}>{m.rounds_b}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
