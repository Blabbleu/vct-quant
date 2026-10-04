import { useState } from "react";
import { useResults, useSnapshot } from "../lib/api";
import { ModelRecord, UpNext } from "../components/matches/RailPanels";
import { eloWinProbability } from "../lib/format";
import { Failure, Loading } from "../components/ui";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import PipBar from "../components/arena/PipBar";
import { Chip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import SectionHead from "../components/arena/SectionHead";
import { LOW_DATA_MATCHES } from "../lib/constants";
import { PageFade, Reveal, CountUp } from "../lib/motion";
import "./Rankings.css";

export default function Rankings() {
  const { data, error, loading } = useSnapshot();
  const results = useResults();
  const [a, setA] = useState(0);
  const [b, setB] = useState(1);
  if (loading) return <Loading what="rankings" />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const rows = data.rankings;
  const ta = rows[a], tb = rows[b];
  const p = ta && tb ? eloWinProbability(ta.elo, tb.elo) : 0.5;

  return (
    <PageFade className="page-fade">
      <header className="rankings-head">
        <h1 className="rankings-title">Rankings</h1>
        <p className="rankings-lede">
          Elo rating of every active Tier-1 team this {data.season} season. Higher is stronger; a team with
          few rated matches this season has a shakier number.
        </p>
      </header>

      <div className="arena-grid">
        <div className="arena-grid-main">
          <SectionHead title="Elo table" right={<span className="muted small num">{rows.length} teams</span>} />
          <div className="rankings-table">
            <div className="rankings-row rankings-row-head">
              <span>#</span><span>Team</span><span className="right">Rating</span><span className="right">Matches</span>
            </div>
            {rows.map((r, idx) => {
              const lowData = r.matches < LOW_DATA_MATCHES;
              return (
                <Reveal className="rankings-row" key={r.team} index={Math.min(idx, 12)}>
                  <span className="rankings-i num">{r.rank}</span>
                  <span className="rankings-team">
                    <LogoSlot src={r.logo} name={r.team} tag={r.tag} size={20} />
                    <span className="rankings-name">
                      <span className="rankings-name-tag"><TeamLabel name={r.team} tag={r.tag} mode="tag" /></span>
                      <span className="rankings-name-full"><TeamLabel name={r.team} tag={r.tag} mode="full" /></span>
                      {lowData && <Chip variant="ghost">LOW DATA</Chip>}
                    </span>
                  </span>
                  <span className="rankings-rating num">{r.elo.toFixed(0)}</span>
                  <span className="rankings-matches num">{r.matches}</span>
                </Reveal>
              );
            })}
          </div>
        </div>

        <div className="arena-grid-aside rankings-h2h-aside">
          <Panel cut="l" frame="line">
            <div className="pad">
              <SectionHead title="Head to head" />
              <div className="rankings-h2h-picks">
                <select value={a} onChange={e => setA(Number(e.target.value))} aria-label="Team A">
                  {rows.map((r, i) => <option key={r.team} value={i}>{r.tag ? `${r.team} (${r.tag})` : r.team}</option>)}
                </select>
                <span className="rankings-h2h-vs num">vs</span>
                <select value={b} onChange={e => setB(Number(e.target.value))} aria-label="Team B">
                  {rows.map((r, i) => <option key={r.team} value={i}>{r.tag ? `${r.team} (${r.tag})` : r.team}</option>)}
                </select>
              </div>
              {a === b ? (
                <p className="muted small" style={{ marginTop: 16 }}>Pick two different teams.</p>
              ) : (
                <>
                  <div className="rankings-h2h-odds">
                    <span className="rankings-h2h-side">
                      <LogoSlot src={ta.logo} name={ta.team} tag={ta.tag} size={34} />
                      <span className={`rankings-h2h-pct num${p >= 0.5 ? " favoured" : ""}`}>{(p * 100).toFixed(1)}</span>
                      <TeamLabel name={ta.team} tag={ta.tag} mode="tag" />
                    </span>
                    <div className="rankings-h2h-mid">
                      <span className="vs num">vs</span>
                    </div>
                    <span className="rankings-h2h-side right">
                      <LogoSlot src={tb.logo} name={tb.team} tag={tb.tag} size={34} />
                      <span className={`rankings-h2h-pct num${p < 0.5 ? " favoured" : ""}`}><CountUp value={100 - p * 100} /></span>
                      <TeamLabel name={tb.team} tag={tb.tag} mode="tag" />
                    </span>
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <PipBar pA={p} />
                  </div>
                </>
              )}
              <p className="rankings-h2h-note small">Neutral-stage series odds. Model is Elo ratings only: no map veto or roster news.</p>
            </div>
          </Panel>
          <UpNext fixtures={data.fixtures} index={1} />
          <ModelRecord results={results} index={2} />
        </div>
      </div>
    </PageFade>
  );
}
