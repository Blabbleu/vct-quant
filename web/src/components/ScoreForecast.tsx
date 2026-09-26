import { pct } from "../lib/format";

/** Exact series-score forecast derived from the series odds and the format. */
export default function ScoreForecast({ scores, bestOf, teamA, teamB }: {
  scores: { score: string; p: number }[]; bestOf: number; teamA: string; teamB: string;
}) {
  const wins = (bestOf + 1) / 2;
  const top = Math.max(...scores.map(s => s.p));
  const expected = scores.reduce((sum, s) => {
    const [a, b] = s.score.split("-").map(Number);
    return sum + (a + b) * s.p;
  }, 0);
  return (
    <section className="panel pad">
      <h2>Series score</h2>
      <p className="muted small">Best of {bestOf}. Each map treated as the same coin, weighted so the scores add up to the series odds above; map picks and veto are not modelled. Expected maps played: {expected.toFixed(2)}.</p>
      <div className="scores">
        {scores.map(s => {
          const aWon = s.score.startsWith(`${wins}-`);
          return (
            <div className="score-row" key={s.score}>
              <span className="who small">{aWon ? teamA : teamB}</span>
              <b className="num">{aWon ? s.score : s.score.split("-").reverse().join("-")}</b>
              <span className="bar-wrap"><i className={`bar ${aWon ? "" : "b"}`} style={{ width: `${(s.p / top) * 100}%` }} /></span>
              <span className="num small">{pct(s.p, 0)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
