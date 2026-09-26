import type { ResultMap } from "../../lib/types";
import "./MapStrip.css";

/**
 * Map-by-map strip for a finished series: one cut-corner cell per map with
 * the map name and each side's round score, the winner's rounds in
 * --result. When round scores are not in the feed yet (`maps.length === 0`)
 * renders the spec's placeholder state: bracketed [MAP] cells in --text-ph
 * for as many maps as were actually played.
 */
export default function MapStrip({
  maps, mapsPlayed, teamA, teamB,
}: {
  maps: ResultMap[]; mapsPlayed: number; teamA: string; teamB: string;
}) {
  if (maps.length === 0) {
    return (
      <div className="mapstrip">
        {Array.from({ length: Math.max(1, mapsPlayed) }, (_, i) => (
          <div className="mapstrip-cell mapstrip-cell-placeholder cut-m" key={i}>
            <span className="mapstrip-map num">[MAP]</span>
            <span className="mapstrip-score num">[SCORE]</span>
          </div>
        ))}
      </div>
    );
  }
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
