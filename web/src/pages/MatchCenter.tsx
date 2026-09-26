import { Link, useParams } from "react-router-dom";
import { useMovement, useSnapshot } from "../lib/api";
import { liquid, pct, relative, when } from "../lib/format";
import LineChart from "../components/LineChart";
import ResultPanel from "../components/ResultPanel";
import HeadToHeadPanel from "../components/HeadToHead";
import TeamLogo from "../components/TeamLogo";
import TeamName from "../components/TeamName";
import { Failure, Loading, PageHead, SplitBar, Tile } from "../components/ui";

export default function MatchCenter() {
  const id = Number(useParams().id);
  const snap = useSnapshot();
  const move = useMovement(id);
  if (!Number.isSafeInteger(id) || id <= 0) return <Failure error="Not a match ID." />;
  if (snap.loading || move.loading) return <Loading what="match" />;
  if (snap.error || move.error) return <Failure error={(snap.error || move.error) as string} />;

  const f = snap.data?.fixtures.find(x => x.match_id === id);
  const m = move.data;
  if (!f && !m) return <Failure error="This match is not in the forecast log." />;

  const teamA = f?.team_a ?? m!.team_a, teamB = f?.team_b ?? m!.team_b;
  const logoA = f?.logo_a ?? m?.logo_a ?? null, logoB = f?.logo_b ?? m?.logo_b ?? null;
  const tagA = f?.tag_a ?? m?.tag_a ?? null, tagB = f?.tag_b ?? m?.tag_b ?? null;
  const keyA = m?.team_a_key, keyB = m?.team_b_key;
  const idA = keyA && /^[1-9]\d*$/.test(keyA) && Number.isSafeInteger(Number(keyA)) ? keyA : null;
  const idB = keyB && /^[1-9]\d*$/.test(keyB) && Number.isSafeInteger(Number(keyB)) ? keyB : null;
  const start = f?.start ?? m!.scheduled_at;
  const last = m?.points.at(-1);
  const p = f?.p_a ?? last?.elo ?? 0.5;
  const market = f ? f.market : last?.market ?? null;
  const trusted = f ? liquid(f.spread, f.volume) : market != null;
  const first = m?.points[0];
  const drift = first && last ? last.elo - first.elo : null;
  const bo = f?.best_of ?? 3;
  const sweep = f?.p_sweep ?? null;

  return (
    <>
      <Link to="/matches" className="back">← All matches</Link>
      <PageHead eyebrow={f ? `${f.event} · ${f.series}` : `Match #${id}`}
        title={<>{teamA} <span className="vs">vs</span> {teamB}</>}>
        {when(start)} ({relative(start)}){f?.best_of ? ` · best of ${f.best_of}` : ""}
      </PageHead>

      <section className="panel pad">
        <div className="odds">
          <div className="side"><TeamLogo src={logoA} name={teamA} size={56} /><div className="big num">{pct(p)}</div><div className="muted small">{idA ? <Link className="team-link" to={`/team/${idA}`}><TeamName name={teamA} tag={tagA} mode="auto" /> →</Link> : <TeamName name={teamA} tag={tagA} mode="auto" />}</div></div>
          <div className="odds-mid"><SplitBar p={p} /><div className="muted small center">{m?.result ? "last pre-start model odds" : "model series odds"}</div></div>
          <div className="side right"><TeamLogo src={logoB} name={teamB} size={56} /><div className="big num dim">{pct(1 - p)}</div><div className="muted small">{idB ? <Link className="team-link" to={`/team/${idB}`}><TeamName name={teamB} tag={tagB} mode="auto" /> →</Link> : <TeamName name={teamB} tag={tagB} mode="auto" />}</div></div>
        </div>
      </section>

      {m?.result && <ResultPanel r={m.result} teamA={teamA} teamB={teamB} />}

      <div className="tiles">
        <Tile value={market == null ? "–" : pct(market)} label={<>Market for {teamA}{market != null && !trusted ? " · thin, low trust" : ""}</>} />
        <Tile value={market == null ? "–" : `${p - market > 0 ? "+" : ""}${((p - market) * 100).toFixed(1)} pts`} label="Model minus market" />
        {sweep != null && <Tile value={pct(sweep, 0)} label={`Ends ${bo === 5 ? "3-0" : "2-0"} either way`} />}
        {drift != null && <Tile value={`${drift > 0 ? "+" : ""}${(drift * 100).toFixed(1)} pts`} label={`Model move since ${when(first!.observed_at)}`} />}
      </div>

      {f && (
        <section className="panel pad">
          <h2>Ratings</h2>
          <div className="kv"><span><TeamName name={teamA} tag={tagA} /></span><b className="num">{f.elo_a.toFixed(0)}</b><span className="muted small">{f.matches_a} rated matches</span></div>
          <div className="kv"><span><TeamName name={teamB} tag={tagB} /></span><b className="num">{f.elo_b.toFixed(0)}</b><span className="muted small">{f.matches_b} rated matches</span></div>
          <p className="muted small">A 100-point Elo edge is roughly 64% to win the series.</p>
        </section>
      )}

      {m?.recent_form && (
        <section className="panel pad">
          <h2>Recent Tier-1 form</h2>
          <p className="muted small">Last five played series known at the latest forecast refresh; excludes undated results, forfeits, draws and anonymous teams. Not an adjustment to the odds.</p>
          {([['a', teamA], ['b', teamB]] as const).map(([side, name]) => (
            <div key={side}>
              <h3>{name}</h3>
              {m.recent_form[side].length ? m.recent_form[side].map(row => (
                <div className="kv" key={row.match_id}>
                  <b className="num">{row.result}</b>
                  <span>vs {row.opponent}</span>
                  <span className="muted small">{new Date(row.completed_at).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" })}</span>
                </div>
              )) : <p className="muted small">No eligible played series in the recorded history.</p>}
            </div>
          ))}
        </section>
      )}

      {m?.head_to_head && <HeadToHeadPanel h={m.head_to_head} teamA={teamA} teamB={teamB} />}

      {m?.map_pool && (
        <section className="panel pad">
          <h2>Map history</h2>
          <p className="muted small">Each side’s last 20 played Tier-1 maps with recorded scores before the latest forecast day. Historical results, not map-specific odds or likely veto picks; small samples can mislead.</p>
          {([['a', teamA], ['b', teamB]] as const).map(([side, name]) => (
            <div key={side}>
              <h3>{name}</h3>
              {m.map_pool[side].length ? <div className="scroll"><table>
                <thead><tr><th>Map</th><th className="n">W / played</th><th className="n">Win %</th><th className="n">Round share</th></tr></thead>
                <tbody>{m.map_pool[side].map(row => (
                  <tr key={row.map}><td>{row.map}</td><td className="n">{row.won} / {row.played}</td>
                    <td className="n">{pct(row.won / row.played, 0)}</td><td className="n">{pct(row.round_share, 0)}</td></tr>
                ))}</tbody>
              </table></div> : <p className="muted small">No scored Tier-1 maps in the recorded history.</p>}
            </div>
          ))}
        </section>
      )}

      {m && m.points.length > 0 && (
        <section className="panel pad">
          <div className="head"><h2>How the odds moved</h2>
            <span className="legend"><i className="swatch elo" />Model <i className="swatch mkt" />Market</span></div>
          <LineChart points={m.points} />
          <p className="muted small">Chance of {teamA} winning. Dots are refreshes of our forecast log ({m.points.length} so far), not a live price feed.</p>
          <details>
            <summary>All {m.points.length} snapshots</summary>
            <div className="scroll"><table>
              <thead><tr><th>When</th><th className="n">Model</th><th className="n">Market</th><th className="n">Spread</th></tr></thead>
              <tbody>{[...m.points].reverse().map(pt => (
                <tr key={pt.observed_at}><td>{when(pt.observed_at)}</td><td className="n">{pct(pt.elo)}</td>
                  <td className="n">{pct(pt.market)}</td><td className="n">{pct(pt.spread)}</td></tr>
              ))}</tbody>
            </table></div>
          </details>
        </section>
      )}

      {f && <p className="small"><a href={f.url} target="_blank" rel="noreferrer">Match page on vlr.gg ↗</a></p>}
    </>
  );
}
