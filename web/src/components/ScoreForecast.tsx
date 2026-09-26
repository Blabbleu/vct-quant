import SeriesScoreBars from "./arena/SeriesScoreBars";
import { COPY } from "../lib/constants";

/**
 * Pre-match series-score distribution: the spec's outcome tiles, plus the
 * fixed "derived from the series chance" honesty line and the sweep-chance
 * note (both scores that end the series 2-0 either way, or 3-0 for Bo5).
 */
export default function ScoreForecast({ scores, bestOf, teamA, teamB }: {
  scores: { score: string; p: number }[]; bestOf: number; teamA: string; teamB: string;
}) {
  const wins = (bestOf + 1) / 2;
  const sweepP = scores.filter(s => {
    const [a, b] = s.score.split("-").map(Number);
    return a === 0 || b === 0;
  }).reduce((sum, s) => sum + s.p, 0);
  const expected = scores.reduce((sum, s) => {
    const [a, b] = s.score.split("-").map(Number);
    return sum + (a + b) * s.p;
  }, 0);
  return (
    <div className="series-score">
      <SeriesScoreBars scores={scores} bestOf={bestOf} teamA={teamA} teamB={teamB} />
      <p className="muted small">
        {COPY.outcomeSplit} Sweep ({wins}-0 either way): {(sweepP * 100).toFixed(1)}%. Expected maps played: {expected.toFixed(2)}.
      </p>
    </div>
  );
}
