import { useState } from "react";
import { useSnapshot } from "../lib/api";
import { eloWinProbability, pct } from "../lib/format";
import { Failure, Loading, PageHead, SplitBar } from "../components/ui";

export default function Rankings() {
  const { data, error, loading } = useSnapshot();
  const [a, setA] = useState(0);
  const [b, setB] = useState(1);
  if (loading) return <Loading what="rankings" />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const rows = data.rankings;
  const lo = Math.min(...rows.map(r => r.elo)) - 40, hi = Math.max(...rows.map(r => r.elo));
  const ta = rows[a], tb = rows[b];
  const p = ta && tb ? eloWinProbability(ta.elo, tb.elo) : 0.5;
  return (
    <>
      <PageHead eyebrow={`${data.season} season`} title="Power rankings">
        Elo rating of every active Tier-1 team. Higher is stronger; a team with few matches this season has a shakier rating.
      </PageHead>

      <section className="panel pad">
        <h2>Head to head</h2>
        <div className="picks">
          <select value={a} onChange={e => setA(Number(e.target.value))} aria-label="Team A">
            {rows.map((r, i) => <option key={r.team} value={i}>{r.team}</option>)}
          </select>
          <span className="vs">vs</span>
          <select value={b} onChange={e => setB(Number(e.target.value))} aria-label="Team B">
            {rows.map((r, i) => <option key={r.team} value={i}>{r.team}</option>)}
          </select>
        </div>
        {a === b ? <p className="muted">Pick two different teams.</p> : (
          <div className="odds">
            <div className="big num">{pct(p)}</div>
            <div className="odds-mid"><SplitBar p={p} /></div>
            <div className="big num dim right">{pct(1 - p)}</div>
          </div>
        )}
        <p className="muted small">Series odds on a neutral stage, from ratings alone: no map veto or roster news.</p>
      </section>

      <section className="panel">
        {rows.map(r => (
          <div className="rank" key={r.team}>
            <span className="i num">{r.rank}</span>
            <b className="ellipsis">{r.team}</b>
            <span className="bar-wrap"><i className="bar" style={{ width: `${((r.elo - lo) / (hi - lo)) * 100}%` }} /></span>
            <span className="val num">{r.elo.toFixed(0)} <em>{r.matches}m</em></span>
          </div>
        ))}
      </section>
    </>
  );
}
