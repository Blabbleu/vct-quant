import { Link, useParams } from "react-router-dom";
import { Failure, Loading, PageHead, Tile } from "../components/ui";
import { usePlayerProfile } from "../lib/api";

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

  return <>
    <Link to="/matches" className="back">← All matches</Link>
    <PageHead eyebrow="Tier-1 player" title={data.handle}>
      Exact vlr.gg player ID {data.player_id}{data.country ? ` · ${data.country.toUpperCase()}` : ""} · recorded maps only
    </PageHead>
    <div className="tiles">
      <Tile value={data.recorded_maps} label="Recorded Tier-1 maps" />
      <Tile value={data.agents.length} label="Agents in recorded maps" />
      <Tile value={data.teams.length} label="Teams in recorded maps" />
    </div>
    <p className="muted small">{data.note} Agent/team counts cover all eligible maps; the list below shows the latest 20.</p>
    <div className="grid-2">
      <section className="panel pad">
        <h2>Agent history</h2>
        {data.agents.length ? data.agents.map(a => <div className="team-row" key={a.agent}>
          <span>{a.agent}</span><span className="num">{a.maps} {a.maps === 1 ? "map" : "maps"}</span>
        </div>) : <p className="muted small">No scored Tier-1 maps recorded.</p>}
      </section>
      <section className="panel pad">
        <h2>Team history</h2>
        {data.teams.length ? data.teams.map(t => <div className="team-row" key={`${t.team_id}:${t.name}`}>
          <Link to={`/team/${t.team_id}`}>{t.name}</Link><span className="num">{t.maps} {t.maps === 1 ? "map" : "maps"}</span>
        </div>) : <p className="muted small">No recorded teams yet.</p>}
      </section>
    </div>
    <section className="panel pad">
      <h2>Recent map stats</h2>
      {data.maps.length ? data.maps.map(m => <div className="player-map" key={`${m.match_id}:${m.map_number}`}>
        <div className="team-row">
          <span><span className="muted small">{dateOnly(m.completed_at)} · {m.map} · {m.agent || "Unknown agent"}</span><br />
            <Link to={`/team/${m.team_id}`}>{m.team}</Link> vs <Link to={`/team/${m.opponent_id}`}>{m.opponent}</Link></span>
          <span className="right"><b className={m.result === "W" ? "team-win num" : "num"}>{m.result} {m.rounds_for}–{m.rounds_against}</b><br />
            <a className="small" href={`https://www.vlr.gg/${m.match_id}`} target="_blank" rel="noopener noreferrer">Source ↗</a></span>
        </div>
        <div className="muted small num">K/D/A {m.kills ?? "—"}/{m.deaths ?? "—"}/{m.assists ?? "—"} · ACS {m.acs?.toFixed(0) ?? "—"} · rating {m.rating?.toFixed(2) ?? "—"}</div>
      </div>) : <p className="muted small">No eligible map statistics yet.</p>}
    </section>
  </>;
}
