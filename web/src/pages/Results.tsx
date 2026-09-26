import { useState } from "react";
import { Link } from "react-router-dom";
import { useResults } from "../lib/api";
import type { ResultRow } from "../lib/types";
import { num, pct } from "../lib/format";
import TeamLogo from "../components/TeamLogo";
import TeamName from "../components/TeamName";
import { Failure, Loading, PageHead, Tile } from "../components/ui";

const TIER_LABEL: Record<string, string> = { "1": "Tier 1", "2": "Tier 2", "3": "Game Changers" };
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined,
  { timeZone: "UTC", weekday: "short", month: "short", day: "numeric" });

function ResultCard({ r }: { r: ResultRow }) {
  const res = r.result;
  const ok = res.status === "verified";
  const winnerP = ok ? (res.winner === "a" ? r.p_a : 1 - r.p_a) : null;
  return (
    <Link to={`/match/${r.match_id}`} className="fx-card">
      <div className="fx-meta">
        <span>{day(r.scheduled_at)} UTC</span>
        <span className="muted">{r.tier != null ? TIER_LABEL[String(r.tier)] ?? `Tier ${r.tier}` : ""}</span>
      </div>
      <div className="fx-teams">
        <span className={`team${ok && res.winner === "a" ? " team-win" : ""}`}>
          <TeamLogo src={r.logo_a} name={r.team_a} size={24} /><b><TeamName name={r.team_a} tag={r.tag_a} mode="auto" /></b>
        </span>
        <span className="vs num score">{ok ? `${res.maps_a}–${res.maps_b}` : "?"}</span>
        <span className={`team right${ok && res.winner === "b" ? " team-win" : ""}`}>
          <b><TeamName name={r.team_b} tag={r.tag_b} mode="auto" /></b><TeamLogo src={r.logo_b} name={r.team_b} size={24} />
        </span>
      </div>
      <div className="muted small ellipsis">{r.event}{r.series ? ` · ${r.series}` : ""}{r.best_of ? ` · Bo${r.best_of}` : ""}</div>
      {ok ? (
        <div className="fx-nums">
          <span>Model had winner at <b className="num">{pct(winnerP)}</b></span>
          {r.market_a != null && <span className="muted">market {pct(res.winner === "a" ? r.market_a : 1 - r.market_a)}</span>}
          {r.favourite_won === false && <span className="chip gap">upset</span>}
          <span className="muted small">log loss {num(r.log_loss, 3)}</span>
        </div>
      ) : (
        <div className="small muted">Result not verified ({res.reason}); not scored.</div>
      )}
    </Link>
  );
}

export default function Results() {
  const { data, error, loading } = useResults();
  const [tier, setTier] = useState("all");
  if (loading) return <Loading what="results" />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const tiers = [...new Set(data.rows.map(r => String(r.tier)))].sort();
  const shown = tier === "all" ? data.rows : data.rows.filter(r => String(r.tier) === tier);
  return (
    <>
      <PageHead eyebrow="Finished" title="Results">
        Every logged match that has finished, with the last forecast the desk showed before kickoff. A result is scored only
        once the stored score, winner and both teams check out; anything else is listed as unverified.
      </PageHead>
      {Object.keys(data.by_tier).length > 0 && (
        <div className="tiles">
          {Object.entries(data.by_tier).sort().map(([t, s]) => (
            <Tile key={t} value={`${s.favourite_won}/${s.verified}`}
              label={`${TIER_LABEL[t] ?? `Tier ${t}`}: favourite won · log loss ${num(s.log_loss, 3)}`} />
          ))}
        </div>
      )}
      <p className="muted small">
        A handful of matches says little about the model; the backtest and shadow comparison live on
        {" "}<Link to="/track-record">Track record</Link>. Game Changers is rated in its own pool.
      </p>
      {tiers.length > 1 && (
        <div className="filters">
          <button className={tier === "all" ? "on" : ""} onClick={() => setTier("all")}>All</button>
          {tiers.map(t => <button key={t} className={tier === t ? "on" : ""} onClick={() => setTier(t)}>{TIER_LABEL[t] ?? `Tier ${t}`}</button>)}
        </div>
      )}
      {shown.length === 0 && <p className="muted">No finished logged matches yet.</p>}
      <div className="cards">{shown.map(r => <ResultCard key={r.match_id} r={r} />)}</div>
    </>
  );
}
