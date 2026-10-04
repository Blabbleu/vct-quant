import { Link } from "react-router-dom";
import type { Fixture } from "../../lib/types";
import { LOW_DATA_MATCHES, WIDE_SPREAD } from "../../lib/constants";
import LogoSlot from "./LogoSlot";
import TeamLabel from "./TeamLabel";
import PipBar from "./PipBar";
import GapChip from "./GapChip";
import { Chip, CountdownChip } from "./Chip";
import Panel from "./Panel";
import { CountUp } from "../../lib/motion";
import "./MatchRow.css";

const time24 = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const pct1 = (p: number) => (p * 100).toFixed(1);

/**
 * One upcoming match, the spec's "Match card (Matches list)": kick-off +
 * countdown + stage/BO, logo/tag/% on both sides, the pip bar with the
 * market notch, and the market read (gap chip, or NO PRICE YET). The whole
 * card is one link to the match page. Used by both Home and Matches.
 */
export default function MatchRow({ f }: { f: Fixture }) {
  const favA = f.p_a >= 0.5;
  const hasMarket = f.market != null;
  const wideSpread = f.spread != null && f.spread > WIDE_SPREAD;
  const lowDataA = f.matches_a < LOW_DATA_MATCHES;
  const lowDataB = f.matches_b < LOW_DATA_MATCHES;
  const anyLowData = lowDataA || lowDataB;
  const favTag = (favA ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)).toUpperCase();
  const stageLine = `${f.event} \u00B7 ${f.series}${f.best_of ? ` \u00B7 Bo${f.best_of}` : ""}`;
  const lowDataSide = lowDataA && (!lowDataB || f.matches_a <= f.matches_b)
    ? { tag: (f.tag_a ?? f.team_a).toUpperCase(), n: f.matches_a }
    : lowDataB ? { tag: (f.tag_b ?? f.team_b).toUpperCase(), n: f.matches_b } : null;

  return (
    <Panel cut="l" frame="line" lift className="match-row-panel">
      <Link to={`/match/${f.match_id}`} className="match-row-link">
        <div className="match-row-top">
          <span className="match-row-time-wrap">
            <span className="num match-row-time">{time24.format(new Date(f.start))}</span>
            <CountdownChip iso={f.start} />
          </span>
          <span className="match-row-stage muted small ellipsis num">{stageLine}</span>
        </div>

        <div className="match-row-teams">
          <div className="match-row-side">
            <LogoSlot src={f.logo_a} name={f.team_a} tag={f.tag_a} size={34} />
            <TeamLabel name={f.team_a} tag={f.tag_a} mode="tag" />
            {lowDataA && <Chip variant="ghost">LOW DATA</Chip>}
          </div>
          <span className={`num match-row-pct${favA ? " match-row-pct-fav" : " match-row-pct-dim"}`}>
            <CountUp value={f.p_a * 100} />
          </span>
          <span className="vs">vs</span>
          <span className={`num match-row-pct${!favA ? " match-row-pct-fav" : " match-row-pct-dim"}`}>
            <CountUp value={(1 - f.p_a) * 100} />
          </span>
          <div className="match-row-side match-row-side-right">
            {lowDataB && <Chip variant="ghost">LOW DATA</Chip>}
            <TeamLabel name={f.team_b} tag={f.tag_b} mode="tag" />
            <LogoSlot src={f.logo_b} name={f.team_b} tag={f.tag_b} size={34} />
          </div>
        </div>

        <PipBar pA={f.p_a} market={f.market} lowData={anyLowData} />

        <div className="match-row-bottom">
          {hasMarket && (
            <span className="num small match-row-market">
              MKT{" "}
              <span className={wideSpread ? "muted" : "match-row-market-value"}>{pct1(f.market as number)}</span>
              {" \u00B7 "}
              <span className={wideSpread ? "muted" : "match-row-market-value"}>{pct1(1 - (f.market as number))}</span>
            </span>
          )}
          <GapChip model={f.p_a} market={f.market} spread={f.spread} favouredLabel={`${favTag} FAVOURED`} />
        </div>

        {lowDataSide && (
          <p className="match-row-lowdata-note muted small">
            {lowDataSide.tag} has {lowDataSide.n} rated matches this season, so this rating moves fast.
          </p>
        )}
      </Link>
    </Panel>
  );
}
