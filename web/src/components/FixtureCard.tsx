import { Link } from "react-router-dom";
import type { Fixture } from "../lib/types";
import TeamLogo from "./TeamLogo";
import TeamName from "./TeamName";
import { liquid, pct, relative, when } from "../lib/format";

/** One upcoming match: Elo and market on the same 0-100% track for team A. */
export default function FixtureCard({ f }: { f: Fixture }) {
  const hasMarket = f.market != null;
  const trusted = hasMarket && liquid(f.spread, f.volume);
  const gap = trusted ? f.p_a - (f.market as number) : null;
  const fav = f.p_a >= 0.5 ? f.team_a : f.team_b;
  return (
    <Link to={`/match/${f.match_id}`} className="fx-card">
      <div className="fx-meta">
        <span>{when(f.start)}</span>
        <span className="muted">{relative(f.start)}</span>
      </div>
      <div className="fx-teams">
        <span className="team"><TeamLogo src={f.logo_a} name={f.team_a} size={28} /><b><TeamName name={f.team_a} tag={f.tag_a} mode="auto" /></b></span>
        <span className="vs">vs</span>
        <span className="team right"><b><TeamName name={f.team_b} tag={f.tag_b} mode="auto" /></b><TeamLogo src={f.logo_b} name={f.team_b} size={28} /></span>
      </div>
      <div className="muted small ellipsis">{f.event} · {f.series}{f.best_of ? ` · Bo${f.best_of}` : ""}</div>
      <div className="track" aria-hidden>
        <div className="rail" /><div className="mid" />
        {hasMarket && <div className={`dot mkt${trusted ? "" : " faint"}`} style={{ left: `${(f.market as number) * 100}%` }} />}
        <div className="dot elo" style={{ left: `${f.p_a * 100}%` }} />
      </div>
      <div className="fx-nums">
        <span><i className="swatch elo" />Model <b className="num">{pct(f.p_a)}</b></span>
        <span><i className="swatch mkt" />Market <b className="num">{hasMarket ? pct(f.market) : "–"}</b>{hasMarket && !trusted && <em className="muted"> thin</em>}</span>
        {gap != null && Math.abs(gap) >= 0.08 && <span className="chip gap">gap {gap > 0 ? "+" : ""}{(gap * 100).toFixed(0)} pts</span>}
      </div>
      <div className="small muted">Model favourite: {fav}</div>
    </Link>
  );
}
