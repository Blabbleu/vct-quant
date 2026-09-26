import { Link } from "react-router-dom";
import { useSnapshot } from "../lib/api";
import { int, logLoss, num, pct } from "../lib/format";
import Calibration from "../components/Calibration";
import TeamLogo from "../components/TeamLogo";
import TeamName, { shortName } from "../components/TeamName";
import { Failure, Loading, PageHead, Tile } from "../components/ui";

const SHADOW_NAMES: Record<string, string> = {
  ensemble: "Fast/slow ensemble", shrink: "Online shrink", "carry-over": "Roster carry-over",
};

export default function TrackRecord() {
  const { data, error, loading } = useSnapshot();
  if (loading) return <Loading />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const { live, backtest, ledger } = data;
  return (
    <>
      <PageHead eyebrow="Honest scoring" title="Track record">
        Every forecast is saved before the match starts and graded after. Log loss rewards being confidently right and
        punishes being confidently wrong; a coin flip scores 0.693, lower is better.
      </PageHead>

      <div className="tiles">
        <Tile hero value={num(live.log_loss, 3)} label={`Live log loss · ${live.graded} graded`} />
        <Tile value={num(backtest.log_loss, 3)} label={`Backtest · ${int(backtest.n)} matches`} />
        <Tile value="0.693" label="Coin flip" />
        <Tile value={pct(backtest.accuracy)} label="Backtest: picks the winner" />
      </div>

      <section className="panel">
        <div className="head pad"><h2>Graded forecasts</h2><span className="muted small">{live.logged} logged, {live.graded} finished</span></div>
        <div className="scroll"><table>
          <thead><tr><th>Match</th><th className="n">Model</th><th className="n">Market</th><th className="n">Score</th><th>Result</th></tr></thead>
          <tbody>{[...live.rows].reverse().map(r => (
            <tr key={r.match_id}>
              <td><Link to={`/match/${r.match_id}`} className="team"><TeamLogo src={r.logo_a} name={r.team_a} size={18} /><TeamName name={r.team_a} tag={r.tag_a} mode="auto" /> <span className="muted">vs</span> <TeamLogo src={r.logo_b} name={r.team_b} size={18} /><TeamName name={r.team_b} tag={r.tag_b} mode="auto" /></Link></td>
              <td className="n">{pct(r.p)}</td><td className="n">{pct(r.market)}</td>
              <td className="n">{logLoss(r.p, r.won).toFixed(3)}</td>
              <td><span className={r.won ? "verdict shipped" : "verdict rejected"}>{r.won ? `${shortName(r.team_a, r.tag_a) ?? r.team_a} won` : `${shortName(r.team_b, r.tag_b) ?? r.team_b} won`}</span></td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>

      <section className="grid-2">
        <div className="panel pad">
          <h2>Calibration</h2>
          <Calibration buckets={backtest.calibration} />
          <p className="muted small">Dots on the dashed line are well calibrated. Below the line means overconfident.</p>
        </div>
        <div className="panel pad">
          <h2>Models in testing</h2>
          <p className="muted small">Shadow models run alongside but never decide the forecast until they beat it on enough matches.</p>
          {Object.entries(live.shadows).map(([k, s]) => (
            <div className="kv" key={k}><span>{SHADOW_NAMES[k] ?? k}</span>
              <b className="num">{s.shadow.toFixed(3)}</b><span className="muted small">vs {s.elo.toFixed(3)} · n={s.n}</span></div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="pad"><h2>Experiment ledger</h2>
          <p className="muted small">Every idea tested against the model, including the ones that failed.</p></div>
        <div className="scroll"><table>
          <thead><tr><th>Variant</th><th>Tested on</th><th className="n">Score</th><th>Verdict</th></tr></thead>
          <tbody>{ledger.map(r => (
            <tr key={r.name}><td>{r.name}</td><td className="muted">{r.holdout}</td><td className="n">{r.score}</td>
              <td><span className={`verdict ${r.verdict.replace(/\s+/g, "-")}`}>{r.verdict}</span></td></tr>
          ))}</tbody>
        </table></div>
      </section>
    </>
  );
}
