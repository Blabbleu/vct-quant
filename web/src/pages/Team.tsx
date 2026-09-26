import { Link, useParams } from "react-router-dom";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import SectionHead from "../components/arena/SectionHead";
import Panel from "../components/arena/Panel";
import { Chip } from "../components/arena/Chip";
import { EmptyState } from "../components/arena/States";
import { Failure, Loading } from "../components/ui";
import { useTeamProfile } from "../lib/api";
import { num, pct, when } from "../lib/format";
import "./Team.css";

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

  const { summary } = data.logged_results;

  return (
    <>
      <Link to="/matches" className="profile-back">← All matches</Link>
      <header className="profile-head">
        <LogoSlot src={data.logo} name={data.name} tag={data.tag} size={56} />
        <div className="profile-head-text">
          <h1 className="profile-title"><TeamLabel name={data.name} tag={data.tag} mode="full" /></h1>
          <span className="profile-sub">Exact vlr.gg team identity · recorded results and cached fixtures</span>
        </div>
      </header>

      <div className="profile-stats">
        <Chip variant="ghost">{data.record.wins}–{data.record.losses} RECORDED SERIES</Chip>
        {summary.verified > 0 && (
          <Chip variant="ghost">MODEL {summary.model_right}/{summary.model_calls} · LOG LOSS {num(summary.log_loss, 3)}</Chip>
        )}
      </div>
      <p className="muted small">{data.note} These results are descriptive, not an adjustment to the forecast.</p>

      <div className="arena-grid">
        <div className="arena-grid-main">
          <SectionHead title="Model calls on this team" right={<span className="muted small num">{data.logged_results.rows.length}</span>} />
          <p className="muted small">
            Finished Tier-1 matches the desk forecast before kickoff: the last pre-start win chance it gave this
            team, next to the verified result. Too few matches to judge the model on one team; see
            {" "}<Link to="/track-record">Track record</Link>.
          </p>
          {data.logged_results.rows.length ? (
            <div className="profile-list">
              {data.logged_results.rows.map(r => (
                <Link to={`/match/${r.match_id}`} className="profile-row" key={r.match_id}>
                  <div className="profile-row-main">
                    <span className="profile-row-date num">{new Date(r.scheduled_at).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" })}{r.series ? ` · ${r.series}` : ""}</span>
                    <span className="profile-row-opp"><Opponent id={r.opponent_id} name={r.opponent} /></span>
                  </div>
                  <div className="profile-row-right">
                    {r.status === "verified" ? (
                      <span className="profile-row-score num" style={{ color: r.won ? "var(--result)" : "var(--text-3)" }}>
                        {r.won ? "W" : "L"} {r.maps_for}–{r.maps_against}
                      </span>
                    ) : (
                      <span className="profile-row-model">unverified, not scored</span>
                    )}
                    <span className="profile-row-model num">model {pct(r.p_win)}{r.market_win != null ? ` · mkt ${pct(r.market_win)}` : ""}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : <EmptyState title="NO GRADED MATCHES" line="No finished Tier-1 matches of this team in the prediction log yet." />}

          <SectionHead title="Recent results" right={<span className="muted small num">{data.results.length}</span>} />
          <p className="muted small">Up to 20 dated, scored Tier-1 series. Recorded W-L above covers all eligible series, not just this list.</p>
          {data.results.length ? (
            <div className="profile-list">
              {data.results.map(r => (
                <div className="profile-row" key={r.match_id}>
                  <div className="profile-row-main">
                    <span className="profile-row-date num">{new Date(r.completed_at).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" })}</span>
                    <span className="profile-row-opp"><Opponent id={r.opponent_id} name={r.opponent} /></span>
                  </div>
                  <div className="profile-row-right">
                    <span className="profile-row-score num" style={{ color: r.result === "W" ? "var(--result)" : "var(--text-3)" }}>{r.result}</span>
                    <span className="profile-row-model num">{r.maps_for}–{r.maps_against} maps</span>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="NO RESULTS" line="No eligible played results yet." />}
        </div>

        <div className="arena-grid-aside">
          <Panel cut="l" frame="line">
            <div className="pad">
              <SectionHead title="Upcoming fixtures" />
              {data.fixtures.length ? (
                <div className="profile-list">
                  {data.fixtures.map(f => (
                    <div className="profile-row" key={f.match_id}>
                      <div className="profile-row-main">
                        <span className="profile-row-date num">{when(f.scheduled_at)}</span>
                        <span className="profile-row-opp"><Opponent id={f.opponent_id} name={f.opponent} /></span>
                      </div>
                      <div className="profile-row-right">
                        <span className="profile-row-score num">{pct(f.p_win)}</span>
                        <Link to={`/match/${f.match_id}`} className="profile-row-link">Match center →</Link>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <p className="muted small">No future Tier-1 fixtures in the current cache.</p>}
            </div>
          </Panel>

          <Panel cut="l" frame="line">
            <div className="pad">
              <SectionHead title="Recent recorded players" />
              <p className="muted small">
                Exact-ID player appearances in up to {data.recent_lineup.maps_sampled} scored Tier-1 maps
                {data.recent_lineup.latest_map_date ? `, latest ${data.recent_lineup.latest_map_date}` : ""}.
                Historical coverage only, not a current roster, confirmed lineup or forecast input.
                {" "}{data.recent_lineup.latest_match_id && (
                  <a href={`https://www.vlr.gg/${data.recent_lineup.latest_match_id}`} target="_blank" rel="noopener noreferrer">Latest source match ↗</a>
                )}
              </p>
              {data.recent_lineup.players.length ? (
                <div className="profile-tags">
                  {data.recent_lineup.players.map(player => (
                    <div className="profile-tag-row" key={player.player_id}>
                      <Link to={`/player/${player.player_id}`}>{player.handle}</Link>
                      <span className="num muted small">{player.maps} / {data.recent_lineup.maps_sampled} maps</span>
                    </div>
                  ))}
                </div>
              ) : <p className="muted small">No exact-ID player stats in eligible scored maps.</p>}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
