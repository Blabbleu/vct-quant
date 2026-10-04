import { Link } from "react-router-dom";
import Panel from "../arena/Panel";
import LogoSlot from "../arena/LogoSlot";
import TeamLabel from "../arena/TeamLabel";
import { Chip } from "../arena/Chip";
import { PickMarker } from "./RailPanels";
import "./FinishedCard.css";
import { pickHit, pickSide, stageLabel } from "../../lib/matchesData";
import type { ResultRow } from "../../lib/types";

const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const p0 = (p: number) => `${(p * 100).toFixed(0)}%`;

/** A graded match: final score, per-map rounds when the feed has them, and how the model's pick did. */
export default function FinishedCard({ r }: { r: ResultRow }) {
  const aWon = r.result.winner === "a";
  const hit = pickHit(r);
  const pick = pickSide(r);
  const pickTag = (pick.side === "a" ? (r.tag_a ?? r.team_a) : (r.tag_b ?? r.team_b)).toUpperCase();
  const mkt = r.market_a != null ? (pick.side === "a" ? r.market_a : 1 - r.market_a) : null;
  return (
    <Panel cut="l" frame="line" lift className="match-row-panel finished-card">
      <Link to={`/match/${r.match_id}`} className="match-row-link">
        <div className="match-row-top">
          <span className="num match-row-time">{when(r.scheduled_at)}</span>
          <span className="match-row-stage muted small ellipsis num" title={`${r.event} \u00B7 ${r.series ?? ""}`}>
            {stageLabel({ series: r.series ?? "", best_of: r.best_of })}
          </span>
        </div>
        <div className="finished-teams">
          <span className={`finished-side${aWon ? " finished-win" : ""}`}>
            <LogoSlot src={r.logo_a} name={r.team_a} tag={r.tag_a} size={34} faded={!aWon} />
            <TeamLabel name={r.team_a} tag={r.tag_a} mode="tag" />
          </span>
          <span className="num finished-score">{r.result.maps_a}&ndash;{r.result.maps_b}</span>
          <span className={`finished-side finished-side-right${!aWon ? " finished-win" : ""}`}>
            <TeamLabel name={r.team_b} tag={r.tag_b} mode="tag" />
            <LogoSlot src={r.logo_b} name={r.team_b} tag={r.tag_b} size={34} faded={aWon} />
          </span>
        </div>
        {r.result.maps.length > 0 && (
          <div className="finished-maps num">
            {r.result.maps.map(mp => (
              <span key={mp.number} className="finished-map cut-s">
                <i>{mp.map}</i>
                <b className={mp.rounds_a > mp.rounds_b ? "finished-map-a" : ""}>{mp.rounds_a}</b>&ndash;<b className={mp.rounds_b > mp.rounds_a ? "finished-map-a" : ""}>{mp.rounds_b}</b>
              </span>
            ))}
          </div>
        )}
        <div className="match-row-bottom">
          <span className="num small match-row-market">
            Model <span className="match-row-market-value" style={{ color: "var(--model)" }}>{pickTag} {p0(pick.p)}</span>
            {mkt != null && <> &middot; MKT <span className="match-row-market-value">{p0(mkt)}</span></>}
          </span>
          <span className="finished-chips">
            {r.favourite_won === false && <Chip variant="ghost">UPSET</Chip>}
            <PickMarker hit={hit} />
          </span>
        </div>
      </Link>
    </Panel>
  );
}
