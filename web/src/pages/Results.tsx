import { useState } from "react";
import { Link } from "react-router-dom";
import { useResults } from "../lib/api";
import type { ResultRow } from "../lib/types";
import { num, pct } from "../lib/format";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import { Chip } from "../components/arena/Chip";
import { EmptyState } from "../components/arena/States";
import { Failure, Loading } from "../components/ui";
import { COPY } from "../lib/constants";
import "./Results.css";

const TIER_LABEL: Record<string, string> = { "1": "Tier 1", "2": "Tier 2", "3": "Game Changers" };
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined,
  { timeZone: "UTC", weekday: "short", month: "short", day: "numeric" });

function ResultRowView({ r }: { r: ResultRow }) {
  const res = r.result;
  const ok = res.status === "verified";
  const winnerP = ok ? (res.winner === "a" ? r.p_a : 1 - r.p_a) : null;
  const winnerMarket = ok && r.market_a != null ? (res.winner === "a" ? r.market_a : 1 - r.market_a) : null;
  const upset = r.favourite_won === false;
  return (
    <Link to={`/match/${r.match_id}`} className="results-row">
      <div className="results-row-meta">
        <span className="results-row-date num">{day(r.scheduled_at)} UTC</span>
        <span className="results-row-event ellipsis">
          {r.tier != null ? TIER_LABEL[String(r.tier)] ?? `Tier ${r.tier}` : ""}
          {r.series ? ` \u00B7 ${r.series}` : ""}
        </span>
      </div>
      <div className="results-row-teams">
        <span className={`results-side${ok && res.winner === "b" ? " results-side-lost" : ""}`}>
          <LogoSlot src={r.logo_a} name={r.team_a} tag={r.tag_a} size={34} faded={ok && res.winner === "b"} />
          <TeamLabel name={r.team_a} tag={r.tag_a} mode="auto" />
        </span>
        <span className="results-score num">{ok ? `${res.maps_a}\u2013${res.maps_b}` : "?"}</span>
        <span className={`results-side right${ok && res.winner === "a" ? " results-side-lost" : ""}`}>
          <LogoSlot src={r.logo_b} name={r.team_b} tag={r.tag_b} size={34} faded={ok && res.winner === "a"} />
          <TeamLabel name={r.team_b} tag={r.tag_b} mode="auto" />
        </span>
      </div>
      {ok ? (
        <div className="results-row-stats">
          <span>Model had winner at <b className="num">{pct(winnerP)}</b></span>
          {winnerMarket != null && <span>market <b className="num">{pct(winnerMarket)}</b></span>}
          {upset && <Chip variant="market">UPSET</Chip>}
          <span className="results-loglos num small">log loss {num(r.log_loss, 3)}</span>
        </div>
      ) : (
        <div className="results-row-unverified">Result not verified ({res.reason}); not scored.</div>
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
      <header className="results-head">
        <h1 className="results-title">Results</h1>
        <p className="results-lede">
          Every logged match that has finished, with the last forecast the desk showed before kickoff.
          A result is scored only once the stored score, winner and both teams check out; anything else
          is listed as unverified.
        </p>
      </header>

      {Object.keys(data.by_tier).length > 0 && (
        <div className="results-summary">
          {Object.entries(data.by_tier).sort().map(([t, s]) => (
            <span key={t} className="small muted">
              {TIER_LABEL[t] ?? `Tier ${t}`}: favourite won <b className="num" style={{ color: "var(--text)" }}>{s.favourite_won}/{s.verified}</b> · log loss <span className="num">{num(s.log_loss, 3)}</span>
            </span>
          ))}
        </div>
      )}
      <p className="muted small">
        A handful of matches says little about the model; the backtest and shadow comparison live on
        {" "}<Link to="/track-record">Track record</Link>. Game Changers is rated in its own pool.
      </p>

      {tiers.length > 1 && (
        <div className="results-filters">
          <button type="button" className={`results-filter-btn${tier === "all" ? " on" : ""}`} onClick={() => setTier("all")}><span>All</span></button>
          {tiers.map(t => (
            <button key={t} type="button" className={`results-filter-btn${tier === t ? " on" : ""}`} onClick={() => setTier(t)}>
              <span>{TIER_LABEL[t] ?? `Tier ${t}`}</span>
            </button>
          ))}
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState
          title={COPY.noMatchesScheduled}
          line="No finished logged matches for this filter yet."
          action={tier !== "all" ? <button type="button" className="btn btn-secondary" onClick={() => setTier("all")}>Show all Tier 1</button> : undefined}
        />
      ) : (
        <div className="results-list">{shown.map(r => <ResultRowView key={r.match_id} r={r} />)}</div>
      )}
    </>
  );
}
