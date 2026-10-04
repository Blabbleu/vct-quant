import { useState } from "react";
import { Link } from "react-router-dom";
import type { Fixture } from "../../lib/types";
import { LOW_DATA_MATCHES, WIDE_SPREAD } from "../../lib/constants";
import LogoSlot from "./LogoSlot";
import TeamLabel from "./TeamLabel";
import PipBar from "./PipBar";
import GapChip from "./GapChip";
import { Chip, CountdownChip } from "./Chip";
import Panel from "./Panel";
import { CountUp, m, useInitial, EASE_OUT, D_BASE, useMinWidth } from "../../lib/motion";
import { stageLabel } from "../../lib/matchesData";
import "./MatchRow.css";

const time24 = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const pct1 = (p: number) => (p * 100).toFixed(1);

/** Exact-score forecast as small labelled bars (a-wins red, b-wins grey), widths relative to the likeliest score. */
function ScoreMini({ f }: { f: Fixture }) {
  const init = useInitial("hidden");
  const scores = f.scores ?? [];
  const top = Math.max(...scores.map(x => x.p), 1e-9);
  const wins = f.best_of ? (f.best_of + 1) / 2 : null;
  return (
    <div className="match-row-scores" style={{ gridTemplateColumns: `repeat(${scores.length}, minmax(0, 1fr))` }}
      role="img" aria-label={`Scoreline forecast: ${scores.map(x => `${x.score} ${(x.p * 100).toFixed(0)}%`).join(", ")}`}>
      {scores.map((x, i) => {
        const aWon = wins != null ? Number(x.score.split("-")[0]) === wins : i < scores.length / 2;
        return (
          <div className="match-row-score" key={x.score}>
            <span className="num match-row-score-label">{x.score.replace("-", "\u2013")}</span>
            <span className="match-row-score-track" aria-hidden="true">
              <m.span
                className={`match-row-score-fill${aWon ? "" : " match-row-score-fill-b"}`}
                style={{ transformOrigin: "0 50%", width: `${Math.max(4, (x.p / top) * 100)}%` }}
                initial={init} whileInView="show" viewport={{ once: true, amount: 0.3 }}
                variants={{ hidden: { scaleX: 0 }, show: { scaleX: 1 } }}
                transition={{ duration: D_BASE, ease: EASE_OUT, delay: 0.08 + i * 0.04 }}
              />
            </span>
            <span className="num match-row-score-pct">{(x.p * 100).toFixed(0)}%</span>
          </div>
        );
      })}
    </div>
  );
}

/** Elo of both sides, the gap, and the sweep chance: the numbers behind the headline percentage. */
function DetailBlock({ f }: { f: Fixture }) {
  const gap = f.elo_a - f.elo_b;
  const leadTag = (gap >= 0 ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)).toUpperCase();
  return (
    <div className="match-row-detail">
      <div className="match-row-detail-stats num">
        <span><i>ELO</i> <b>{Math.round(f.elo_a)}</b> <span className="muted">vs</span> <b>{Math.round(f.elo_b)}</b></span>
        <span className="match-row-detail-gap">{leadTag} +{Math.round(Math.abs(gap))}</span>
        {f.p_sweep != null && <span><i>SWEEP</i> <b>{(f.p_sweep * 100).toFixed(0)}%</b></span>}
      </div>
      {f.scores && f.scores.length > 0 && <ScoreMini f={f} />}
    </div>
  );
}

/**
 * One upcoming match, the spec's "Match card (Matches list)": kick-off +
 * countdown + stage/BO, logo/tag/% on both sides, the pip bar with the
 * market notch, and the market read (gap chip, or NO PRICE YET). The whole
 * card is one link to the match page. Used by both Home and Matches.
 */
export default function MatchRow({ f, detail = true }: { f: Fixture; detail?: boolean }) {
  const roomy = useMinWidth(768);
  const [open, setOpen] = useState(false);
  const favA = f.p_a >= 0.5;
  const hasMarket = f.market != null;
  const wideSpread = f.spread != null && f.spread > WIDE_SPREAD;
  const lowDataA = f.matches_a < LOW_DATA_MATCHES;
  const lowDataB = f.matches_b < LOW_DATA_MATCHES;
  const anyLowData = lowDataA || lowDataB;
  const favTag = (favA ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)).toUpperCase();
  const stageText = stageLabel(f);
  const stageTitle = `${f.event} \u00B7 ${f.series}${f.best_of ? ` \u00B7 Bo${f.best_of}` : ""}`;
  const showDetail = detail && (roomy || open);
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
          <span className="match-row-stage muted small ellipsis num" title={stageTitle}>{stageText}</span>
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
      {detail && (
        <div className="match-row-more">
          {!roomy && (
            <button type="button" className="match-row-toggle num" aria-expanded={open} onClick={() => setOpen(o => !o)}>
              {open ? "Hide scoreline & Elo" : "Scoreline & Elo"}<span aria-hidden="true">{open ? " \u2212" : " +"}</span>
            </button>
          )}
          {showDetail && <DetailBlock f={f} />}
        </div>
      )}
    </Panel>
  );
}
