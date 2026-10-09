import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import Panel from "../arena/Panel";
import SectionHead from "../arena/SectionHead";
import RecordBar from "../arena/RecordBar";
import LogoSlot from "../arena/LogoSlot";
import TeamLabel from "../arena/TeamLabel";
import PipBar from "../arena/PipBar";
import { Chip } from "../arena/Chip";
import { CountUp, Reveal } from "../../lib/motion";
import { biggestMisses, nextPlayoffSeries, pickHit, pickSide, stageLabel, stageParts, verifiedNewestFirst } from "../../lib/matchesData";
import { recordView } from "../../lib/record";
import { localShort } from "../../lib/format";
import type { ChampionsPlayoffs, Fixture, Ranking, ResultRow, ResultsList } from "../../lib/types";
import "./RailPanels.css";

type Async<T> = { data: T | null; error: string | null; loading: boolean };

/** One rail panel: cut-corner frame, section head with a link, staggered reveal. */
export function RailPanel({ title, link, to, index = 0, children }: {
  title: string; link?: string; to?: string; index?: number; children: ReactNode;
}) {
  return (
    <Reveal index={index} className="rail-panel-wrap">
      <Panel cut="m" frame="line">
        <div className="rail-panel">
          <SectionHead title={title} right={to && link ? <Link to={to} className="rail-link num">{link} &rarr;</Link> : undefined} />
          {children}
        </div>
      </Panel>
    </Reveal>
  );
}

const Skeleton = ({ rows = 3 }: { rows?: number }) => (
  <div className="rail-skel" aria-busy="true" aria-label="Loading">
    {Array.from({ length: rows }, (_, i) => <span key={i} className="loading-line" />)}
  </div>
);

const tag = (name: string, t: string | null) => (t ?? name).toUpperCase();

/** Graded Tier 1 record (hits of calls) with log loss next to a coin flip. */
export function ModelRecord({ results, index }: { results: Async<ResultsList>; index?: number }) {
  const rec = recordView(results);
  return (
    <RailPanel title="Model record" link="Track record" to="/track-record" index={index}>
      {rec.kind === "ready" ? (
        <>
          <div className="rail-big">
            <span className="num rail-big-num"><CountUp value={rec.tier.favourite_won} decimals={0} /></span>
            <span className="num rail-big-of">/ {rec.tier.verified}</span>
            <span className="rail-big-cap">favourites won, graded Tier 1</span>
          </div>
          <RecordBar calls={rec.tier.verified} hits={rec.tier.favourite_won} logLoss={rec.tier.log_loss} />
        </>
      ) : rec.kind === "loading" ? <Skeleton rows={3} />
        : rec.kind === "error" ? <p className="muted small">Record unavailable right now ({rec.detail}).</p>
        : <p className="muted small">No graded Tier 1 matches yet this season.</p>}
    </RailPanel>
  );
}

/** HIT / MISS marker for the model's pick. */
export function PickMarker({ hit }: { hit: boolean | null }) {
  if (hit == null) return null;
  return <Chip variant={hit ? "result" : "market"}>{hit ? "HIT" : "MISS"}</Chip>;
}

/** Last graded matches: both tags (winner bright), final map score, the model's pick and whether it landed. */
export function RecentResults({ results, count = 5, index }: { results: Async<ResultsList>; count?: number; index?: number }) {
  const rows = results.data ? verifiedNewestFirst(results.data.rows).slice(0, count) : [];
  return (
    <RailPanel title="Recent results" link="All results" to="/results" index={index}>
      {results.loading ? <Skeleton rows={count} />
        : results.error ? <p className="muted small">Results unavailable right now ({results.error}).</p>
        : rows.length === 0 ? <p className="muted small">No graded matches yet.</p>
        : (
          <ul className="rail-list">
            {rows.map(r => <RecentRow key={r.match_id} r={r} />)}
          </ul>
        )}
    </RailPanel>
  );
}

function RecentRow({ r }: { r: ResultRow }) {
  const aWon = r.result.winner === "a";
  const pick = pickSide(r);
  const pickTag = pick.side === "a" ? tag(r.team_a, r.tag_a) : tag(r.team_b, r.tag_b);
  return (
    <li>
      <Link to={`/match/${r.match_id}`} className="rail-row rail-recent">
        <span className="rail-recent-teams">
          <span className={`rail-side${aWon ? " rail-side-win" : ""}`}>
            <LogoSlot src={r.logo_a} name={r.team_a} tag={r.tag_a} size={20} faded={!aWon} />
            <TeamLabel name={r.team_a} tag={r.tag_a} mode="tag" />
          </span>
          <span className="num rail-score">{r.result.maps_a}&ndash;{r.result.maps_b}</span>
          <span className={`rail-side rail-side-right${!aWon ? " rail-side-win" : ""}`}>
            <TeamLabel name={r.team_b} tag={r.tag_b} mode="tag" />
            <LogoSlot src={r.logo_b} name={r.team_b} tag={r.tag_b} size={20} faded={aWon} />
          </span>
        </span>
        <span className="rail-recent-pick num">
          <span className="muted">Model {pickTag} {(pick.p * 100).toFixed(0)}%</span>
          <PickMarker hit={pickHit(r)} />
        </span>
      </Link>
    </li>
  );
}

/** The Upper Quarterfinal slate from the Champions feed: kick-off, tags and the favourite's chance. */
export function BracketMini({ playoffs, loading, index }: { playoffs: ChampionsPlayoffs | undefined; loading: boolean; index?: number }) {
  const series = nextPlayoffSeries(playoffs);
  const stages = [...new Set(series.map(mm => stageParts(mm.stage).stage).filter(Boolean))];
  return (
    <RailPanel title="Champions bracket" link="Full bracket" to="/champions/2766" index={index}>
      {loading ? <Skeleton rows={4} />
        : series.length === 0 ? <p className="muted small">Playoff matchups not published yet.</p>
        : (
          <>
            {stages.length > 0 && <div className="rail-sub num">{stages.join(" · ")}</div>}
            <ul className="rail-list">
              {series.map(mm => {
                if (!mm.sides || mm.sides.length !== 2) return null;
                const [a, b] = mm.sides;
                const known = a.p_win != null && b.p_win != null;
                const favA = known && (a.p_win as number) >= 0.5;
                const fav = favA ? a : b;
                return (
                  <li key={mm.match_id}>
                    <Link to={`/match/${mm.match_id}`} className="rail-row rail-bracket">
                      <span className="rail-bracket-teams">
                        <LogoSlot src={a.logo} name={a.name} tag={a.tag} size={20} />
                        <b className={favA ? "rail-fav" : ""}>{tag(a.name, a.tag)}</b>
                        <span className="vs">vs</span>
                        <b className={!favA && known ? "rail-fav" : ""}>{tag(b.name, b.tag)}</b>
                        <LogoSlot src={b.logo} name={b.name} tag={b.tag} size={20} />
                      </span>
                      <span className="rail-bracket-meta num">
                        <span className="muted">{mm.start ? localShort(mm.start) : "TBD"}</span>
                        {known && <span className="rail-fav">{tag(fav.name, fav.tag)} {((fav.p_win as number) * 100).toFixed(0)}%</span>}
                      </span>
                      {known && <PipBar pA={a.p_win as number} blocks={20} />}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
    </RailPanel>
  );
}

/** Top of the Elo table. */
export function PowerRanks({ rankings, count = 5, index }: { rankings: Ranking[]; count?: number; index?: number }) {
  const rows = [...rankings].sort((a, b) => a.rank - b.rank).slice(0, count);
  return (
    <RailPanel title="Power rankings" link="Full table" to="/rankings" index={index}>
      <ol className="rail-list rail-ranks">
        {rows.map(r => (
          <li key={r.team}>
            <Link to="/rankings" className="rail-row rail-rank">
              <span className="num rail-rank-i">{r.rank}</span>
              <LogoSlot src={r.logo} name={r.team} tag={r.tag} size={20} />
              <TeamLabel name={r.team} tag={r.tag} mode="auto" />
              <span className="num rail-rank-elo">{r.elo.toFixed(0)}</span>
            </Link>
          </li>
        ))}
      </ol>
    </RailPanel>
  );
}

const kick = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

/** The next few kick-offs with the model's favourite and chance. */
export function UpNext({ fixtures, count = 4, index }: { fixtures: Fixture[]; count?: number; index?: number }) {
  const rows = [...fixtures].sort((a, b) => a.start.localeCompare(b.start)).slice(0, count);
  return (
    <RailPanel title="Up next" link="All matches" to="/matches" index={index}>
      {rows.length === 0 ? <p className="muted small">No matches scheduled.</p> : (
        <ul className="rail-list">
          {rows.map(f => {
            const favA = f.p_a >= 0.5;
            return (
              <li key={f.match_id}>
                <Link to={`/match/${f.match_id}`} className="rail-row rail-bracket">
                  <span className="rail-bracket-teams">
                    <LogoSlot src={f.logo_a} name={f.team_a} tag={f.tag_a} size={20} />
                    <b className={favA ? "rail-fav" : ""}>{tag(f.team_a, f.tag_a)}</b>
                    <span className="vs">vs</span>
                    <b className={!favA ? "rail-fav" : ""}>{tag(f.team_b, f.tag_b)}</b>
                    <LogoSlot src={f.logo_b} name={f.team_b} tag={f.tag_b} size={20} />
                  </span>
                  <span className="rail-bracket-meta num">
                    <span className="muted">{kick.format(new Date(f.start))} &middot; {stageLabel(f)}</span>
                    <span className="rail-fav">{favA ? tag(f.team_a, f.tag_a) : tag(f.team_b, f.tag_b)} {((favA ? f.p_a : 1 - f.p_a) * 100).toFixed(0)}%</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </RailPanel>
  );
}

/** Where the model was most wrong: the graded misses with the highest log loss. */
export function BiggestMisses({ results, count = 3, index }: { results: Async<ResultsList>; count?: number; index?: number }) {
  const rows = results.data ? biggestMisses(results.data.rows, count) : [];
  return (
    <RailPanel title="Biggest misses" link="All results" to="/results" index={index}>
      {results.loading ? <Skeleton rows={count} />
        : results.error ? <p className="muted small">Results unavailable right now ({results.error}).</p>
        : rows.length === 0 ? <p className="muted small">No graded misses yet.</p>
        : (
          <ul className="rail-list">
            {rows.map(r => (
              <li key={r.match_id} className="rail-miss-item">
                <RecentRow r={r} />
                <span className="rail-miss-ll num">log loss {(r.log_loss as number).toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
    </RailPanel>
  );
}
