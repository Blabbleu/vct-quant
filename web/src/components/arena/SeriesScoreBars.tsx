import Panel from "./Panel";
import { Chip } from "./Chip";
import "./SeriesScoreBars.css";

export interface SeriesScoreOutcome { score: string; p: number }

/**
 * Series-score distribution: the spec's "Outcome tiles" -- one cut-corner
 * tile per exact series score (2-0/2-1/1-2/0-2 for a Bo3; 3-0/3-1/3-2/2-3/
 * 1-3/0-3 for a Bo5), each with a % and a 10-block segmented bar. The
 * outcome that actually happened gets a --result frame and a RESULT tag.
 */
export default function SeriesScoreBars({
  scores, bestOf, teamA, teamB, actual,
}: {
  scores: SeriesScoreOutcome[]; bestOf: number; teamA: string; teamB: string;
  actual?: { mapsA: number; mapsB: number } | null;
}) {
  const wins = (bestOf + 1) / 2;
  const top = Math.max(...scores.map(s => s.p));
  return (
    <div className="series-score-grid">
      {scores.map(s => {
        const [a, b] = s.score.split("-").map(Number);
        const aWon = a === wins;
        const who = aWon ? teamA : teamB;
        const isActual = actual != null && actual.mapsA === a && actual.mapsB === b;
        const filled = Math.round((s.p / (top || 1)) * 10);
        return (
          <Panel cut="m" frame={isActual ? "result" : "line"} key={s.score} className="series-score-tile-wrap">
            <div className="series-score-tile">
              <div className="series-score-tile-head">
                <span className="series-score-tile-label ellipsis">{who}</span>
                {isActual && <Chip variant="result">RESULT</Chip>}
              </div>
              <div className="series-score-tile-score num">{aWon ? s.score : s.score.split("-").reverse().join("-")}</div>
              <div className="series-score-tile-track" aria-hidden="true">
                {Array.from({ length: 10 }, (_, i) => (
                  <span key={i} className={`series-score-tile-block${i < filled ? " series-score-tile-block-filled" : ""}${aWon ? "" : " series-score-tile-block-b"}`} />
                ))}
              </div>
              <div className="series-score-tile-pct num">{(s.p * 100).toFixed(1)}%</div>
            </div>
          </Panel>
        );
      })}
    </div>
  );
}
