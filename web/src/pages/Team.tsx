import { Link, useParams } from "react-router-dom";
import TeamLogo from "../components/TeamLogo";
import TeamName from "../components/TeamName";
import { Failure, Loading, PageHead, Tile } from "../components/ui";
import { useTeamProfile } from "../lib/api";
import { num, pct, when } from "../lib/format";

function Opponent({ id, name }: { id: number | null; name: string }) {
  return id ? <Link to={`/team/${id}`}>{name}</Link> : <span>{name}</span>;
}

export default function Team() {
  const rawId = useParams().id ?? "";
  const id = Number(rawId);
  const { data, error, loading } = useTeamProfile(id);
  if (!/^[1-9]\d*$/.test(rawId) || !Number.isSafeInteger(id)) return <Failure error="Not a team ID." />;
  if (loading) return <Loading what="team" />;
  if (error) return <Failure error={error} />;
  if (!data) return <Failure error="No dated Tier-1 results or upcoming fixtures for this team ID." />;

  return <>
    <Link to="/matches" className="back">← All matches</Link>
    <div className="team-title">
      <TeamLogo src={data.logo} name={data.name} size={60} />
      <PageHead eyebrow="Tier-1 team" title={<TeamName name={data.name} tag={data.tag} />}>
        Exact vlr.gg team identity · recorded results and cached fixtures
      </PageHead>
    </div>
    <div className="tiles">
      <Tile value={`${data.record.wins}–${data.record.losses}`} label="Recorded played series (W–L)" />
      <Tile value={data.fixtures.length} label="Upcoming cached fixtures" />
    </div>
    <p className="muted small">{data.note} These results are descriptive, not an adjustment to the forecast.</p>
    <section className="panel pad">
      <h2>Recent recorded players</h2>
      <p className="muted small">Exact-ID player appearances in up to {data.recent_lineup.maps_sampled} scored Tier-1 maps{data.recent_lineup.latest_map_date ? `, latest ${data.recent_lineup.latest_map_date}` : ""}. Historical coverage only — not a current roster, confirmed lineup or forecast input. {data.recent_lineup.latest_match_id && <a href={`https://www.vlr.gg/${data.recent_lineup.latest_match_id}`} target="_blank" rel="noopener noreferrer">Latest source match ↗</a>}</p>
      {data.recent_lineup.players.length ? data.recent_lineup.players.map(player =>
        <div className="team-row" key={player.player_id}>
          <Link to={`/player/${player.player_id}`}>{player.handle}</Link>
          <span className="num muted small">{player.maps} / {data.recent_lineup.maps_sampled} maps</span>
        </div>,
      ) : <p className="muted small">No exact-ID player stats in eligible scored maps.</p>}
    </section>
    <section className="panel pad">
      <h2>Upcoming fixtures</h2>
      {data.fixtures.length ? data.fixtures.map(f =>
        <div className="team-row" key={f.match_id}>
          <span><span className="muted small">{when(f.scheduled_at)}</span><br /><Opponent id={f.opponent_id} name={f.opponent} /></span>
          <span className="right"><b className="num">{pct(f.p_win)}</b><br /><Link to={`/match/${f.match_id}`} className="small">Match center →</Link></span>
        </div>,
      ) : <p className="muted small">No future Tier-1 fixtures in the current cache.</p>}
    </section>
    <section className="panel pad">
      <h2>Model calls on this team</h2>
      <p className="muted small">Finished Tier-1 matches the desk forecast before kickoff: the last pre-start win chance it gave this team, next to the verified result. {data.logged_results.summary.verified > 0 && <>Model favourite won {data.logged_results.summary.model_right}/{data.logged_results.summary.model_calls} · mean log loss {num(data.logged_results.summary.log_loss, 3)} over {data.logged_results.summary.verified}. </>}Too few matches to judge the model on one team; see <Link to="/track-record">Track record</Link>.</p>
      {data.logged_results.rows.length ? data.logged_results.rows.map(r =>
        <div className="team-row" key={r.match_id}>
          <span><span className="muted small">{new Date(r.scheduled_at).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" })}{r.series ? ` · ${r.series}` : ""}</span><br /><Opponent id={r.opponent_id} name={r.opponent} /></span>
          <span className="right">
            {r.status === "verified"
              ? <><b className={r.won ? "team-win num" : "num"}>{r.won ? "W" : "L"} {r.maps_for}–{r.maps_against}</b><br /></>
              : <><span className="muted small">unverified, not scored</span><br /></>}
            <span className="small num">model {pct(r.p_win)}{r.market_win != null ? ` · mkt ${pct(r.market_win)}` : ""}</span><br />
            <Link to={`/match/${r.match_id}`} className="small">Match center →</Link>
          </span>
        </div>,
      ) : <p className="muted small">No finished Tier-1 matches of this team in the prediction log yet.</p>}
    </section>
    <section className="panel pad">
      <h2>Recent results</h2>
      <p className="muted small">Up to 20 dated, scored Tier-1 series. Dates are day-only in the source; recorded W–L above covers all eligible series, not just this list.</p>
      {data.results.length ? data.results.map(r =>
        <div className="team-row" key={r.match_id}>
          <span><span className="muted small">{new Date(r.completed_at).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" })}</span><br /><Opponent id={r.opponent_id} name={r.opponent} /></span>
          <span className="right"><b className={r.result === "W" ? "team-win num" : "num"}>{r.result}</b><br /><span className="muted small num">{r.maps_for}–{r.maps_against} maps</span></span>
        </div>,
      ) : <p className="muted small">No eligible played results yet.</p>}
    </section>
  </>;
}
