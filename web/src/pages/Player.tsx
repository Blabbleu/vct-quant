import { Link, useParams } from "react-router-dom";
import SectionHead from "../components/arena/SectionHead";
import Panel from "../components/arena/Panel";
import { Chip } from "../components/arena/Chip";
import { EmptyState } from "../components/arena/States";
import AgentIcon from "../components/arena/AgentIcon";
import PlayerPhoto from "../components/arena/PlayerPhoto";
import { Failure, Loading } from "../components/ui";
import { usePlayerProfile } from "../lib/api";
import "./Player.css";

function dateOnly(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });
}

export default function Player() {
  const rawId = useParams().id ?? "";
  const id = Number(rawId);
  const { data, error, loading } = usePlayerProfile(id);
  if (!/^[1-9]\d*$/.test(rawId) || !Number.isSafeInteger(id)) return <Failure error="Not a player ID." />;
  if (loading) return <Loading what="player" />;
  if (error) return <Failure error={error} />;
  if (!data) return <Failure error="Player ID not found in recorded history." />;

  return (
    <>
      <Link to="/matches" className="profile-back">← All matches</Link>
      <header className="profile-head">
        <PlayerPhoto src={data.photo} handle={data.handle} size={64} />
        <div className="profile-head-text">
          <h1 className="profile-title">{data.handle}</h1>
          <span className="profile-sub">
            Exact vlr.gg player ID {data.player_id}{data.country ? ` · ${data.country.toUpperCase()}` : ""} · recorded maps only
          </span>
        </div>
      </header>

      <div className="profile-stats">
        <Chip variant="ghost">{data.recorded_maps} RECORDED MAPS</Chip>
        <Chip variant="ghost">{data.agents.length} {data.agents.length === 1 ? "AGENT" : "AGENTS"}</Chip>
        <Chip variant="ghost">{data.teams.length} {data.teams.length === 1 ? "TEAM" : "TEAMS"}</Chip>
      </div>
      <p className="muted small">{data.note} Agent/team counts cover all eligible maps; the list below shows the latest 20.</p>

      <div className="arena-grid">
        <div className="arena-grid-main">
          <SectionHead title="Recent map stats" right={<span className="muted small num">{data.maps.length}</span>} />
          {data.maps.length ? (
            <div className="profile-maps player-maps">
              <div className="player-stat-head">
                <span>Map</span><span>Score</span><span>ACS</span><span>Rating</span><span>K/D/A</span>
              </div>
              {data.maps.map(m => (
                <div className="player-map-row" key={`${m.match_id}:${m.map_number}`}>
                  <div className="player-map-main">
                    <div className="profile-map-meta">
                      <span className="player-agent-label"><AgentIcon agent={m.agent} size={24} />{dateOnly(m.completed_at)} · {m.map} · {m.agent || "Unknown agent"}</span>
                    </div>
                    <div className="profile-map-teams">
                      <Link to={`/team/${m.team_id}`}>{m.team}</Link> vs <Link to={`/team/${m.opponent_id}`}>{m.opponent}</Link>
                    </div>
                  </div>
                  <span className={`player-map-num num player-map-result${m.result === "W" ? " player-map-result-w" : ""}`}>
                    <span className="player-map-num-label">Score</span>{m.result} {m.rounds_for}–{m.rounds_against}
                  </span>
                  <div className="player-map-nums">
                    <span className="player-map-num num"><span className="player-map-num-label">ACS</span>{m.acs?.toFixed(0) ?? "—"}</span>
                    <span className="player-map-num num"><span className="player-map-num-label">Rating</span>{m.rating?.toFixed(2) ?? "—"}</span>
                    <span className="player-map-num num"><span className="player-map-num-label">K/D/A</span>{m.kills ?? "—"}/{m.deaths ?? "—"}/{m.assists ?? "—"}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="NO MAP STATS" line="No eligible map statistics yet." />}
        </div>

        <div className="arena-grid-aside">
          <Panel cut="l" frame="line">
            <div className="pad">
              <SectionHead title="Agent history" />
              {data.agents.length ? (
                <div className="profile-tags">
                  {data.agents.map(a => (
                    <div className="profile-tag-row" key={a.agent}>
                      <span className="player-agent-label"><AgentIcon agent={a.agent} size={24} />{a.agent}</span><span className="num muted small">{a.maps} {a.maps === 1 ? "map" : "maps"}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="muted small">No scored Tier-1 maps recorded.</p>}
            </div>
          </Panel>

          <Panel cut="l" frame="line">
            <div className="pad">
              <SectionHead title="Team history" />
              {data.teams.length ? (
                <div className="profile-tags">
                  {data.teams.map(t => (
                    <div className="profile-tag-row" key={`${t.team_id}:${t.name}`}>
                      <Link to={`/team/${t.team_id}`}>{t.name}</Link><span className="num muted small">{t.maps} {t.maps === 1 ? "map" : "maps"}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="muted small">No recorded teams yet.</p>}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
