import { Link, useParams } from "react-router-dom";
import { useMovement, useSnapshot } from "../lib/api";
import { liquid, pct, relative, when } from "../lib/format";
import { COPY, LOW_DATA_MATCHES } from "../lib/constants";
import LineChart from "../components/LineChart";
import ResultPanel from "../components/ResultPanel";
import ScoreForecast from "../components/ScoreForecast";
import HeadToHeadPanel from "../components/HeadToHead";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import PipBar from "../components/arena/PipBar";
import GapChip from "../components/arena/GapChip";
import { Chip, CountdownChip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import SectionHead from "../components/arena/SectionHead";
import StatCell from "../components/arena/StatCell";
import Banner, { type BannerKind } from "../components/arena/Banner";
import { Failure, Loading } from "../components/ui";
import { PageFade } from "../lib/motion";
import "./MatchCenter.css";

const dayFmt = (iso: string) => new Date(iso).toLocaleDateString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });

export default function MatchCenter() {
  const id = Number(useParams().id);
  const snap = useSnapshot();
  const move = useMovement(id);
  if (!Number.isSafeInteger(id) || id <= 0) return <Failure error="Not a match ID." />;
  if (snap.loading || move.loading) return <Loading what="match" />;
  if (snap.error || move.error) return <Failure error={(snap.error || move.error) as string} />;

  const f = snap.data?.fixtures.find(x => x.match_id === id);
  const m = move.data;
  if (!f && !m) return <Failure error={`No match #${id} in the forecast log.`} />;

  const teamA = f?.team_a ?? m!.team_a, teamB = f?.team_b ?? m!.team_b;
  const logoA = f?.logo_a ?? m?.logo_a ?? null, logoB = f?.logo_b ?? m?.logo_b ?? null;
  const tagA = f?.tag_a ?? m?.tag_a ?? null, tagB = f?.tag_b ?? m?.tag_b ?? null;
  const keyA = m?.team_a_key, keyB = m?.team_b_key;
  const idA = keyA && /^[1-9]\d*$/.test(keyA) && Number.isSafeInteger(Number(keyA)) ? keyA : null;
  const idB = keyB && /^[1-9]\d*$/.test(keyB) && Number.isSafeInteger(Number(keyB)) ? keyB : null;
  const start = f?.start ?? m!.scheduled_at;

  const last = m?.points.at(-1);
  const p = f?.p_a ?? last?.elo ?? 0.5;
  const market = f ? f.market : last?.market ?? null;
  const spread = f?.spread ?? last?.spread ?? null;
  const trusted = market != null && (f ? liquid(f.spread, f.volume) : true);
  const bo = f?.best_of ?? 3;

  const result = m?.result ?? null;
  const verified = result?.status === "verified";
  const finished = result != null;
  const startPassed = new Date(start).getTime() <= Date.now();

  const bannerKind: BannerKind = finished ? "complete" : startPassed ? "live" : "upcoming";
  const bannerText = finished ? "MATCH COMPLETE" : startPassed ? "LIVE" : `KICK-OFF ${when(start)}`;

  const favourite: "a" | "b" = p >= 0.5 ? "a" : "b";
  const hit = verified && result!.winner ? favourite === result!.winner : null;
  const favTeam = favourite === "a" ? teamA : teamB;
  const favPct = favourite === "a" ? p : 1 - p;
  const winnerTeam = verified && result!.winner === "a" ? teamA : verified && result!.winner === "b" ? teamB : null;
  const winnerMarketPct = verified && market != null && result!.winner
    ? (result!.winner === "a" ? market : 1 - market) : null;

  const lowDataTeams = [
    f && f.matches_a < LOW_DATA_MATCHES ? { name: teamA, n: f.matches_a } : null,
    f && f.matches_b < LOW_DATA_MATCHES ? { name: teamB, n: f.matches_b } : null,
  ].filter((x): x is { name: string; n: number } => x != null);

  return (
    <PageFade className="page-fade">
      <Link to="/matches" className="back">&larr; All matches</Link>
      <header className="page-head">
        <h1>{teamA} <span className="vs">vs</span> {teamB}</h1>
        <p className="lede match-meta">
          {f ? `${f.event} \u00B7 ${f.series}` : `Match #${id}`}{bo ? ` \u00B7 Best of ${bo}` : ""}
        </p>
        {!finished && (
          <p className="lede page-head-countdown">
            {when(start)} ({relative(start)}) <CountdownChip iso={start} />
          </p>
        )}
      </header>

      <div className="arena-grid">
        <div className="arena-grid-main">
          <Banner kind={bannerKind} text={bannerText} />

          <Panel cut="l" frame="line" brackets className="match-hero">
            <div className="pad match-hero-in">
              {finished ? (
                <ResultPanel r={result!} teamA={teamA} teamB={teamB} tagA={tagA} tagB={tagB} logoA={logoA} logoB={logoB} />
              ) : (
                <>
                  <div className="match-hero-teams">
                    <div className="match-hero-side">
                      <LogoSlot src={logoA} name={teamA} tag={tagA} size={56} />
                      <div className="match-hero-side-text">
                        <TeamLabel name={teamA} tag={tagA} mode="full" />
                        {idA && <Link className="team-link small" to={`/team/${idA}`}>Team page &rarr;</Link>}
                      </div>
                      <span className={`match-hero-pct match-hero-pct-inline num${favourite === "a" ? " match-hero-pct-fav" : ""}`}>{(p * 100).toFixed(1)}</span>
                    </div>
                    <div className="match-hero-nums">
                      <span className={`match-hero-pct num${favourite === "a" ? " match-hero-pct-fav" : ""}`}>{(p * 100).toFixed(1)}</span>
                      <span className="vs">vs</span>
                      <span className={`match-hero-pct num${favourite === "b" ? " match-hero-pct-fav" : ""}`}>{((1 - p) * 100).toFixed(1)}</span>
                    </div>
                    <div className="match-hero-side match-hero-side-right">
                      <span className={`match-hero-pct match-hero-pct-inline num${favourite === "b" ? " match-hero-pct-fav" : ""}`}>{((1 - p) * 100).toFixed(1)}</span>
                      <div className="match-hero-side-text match-hero-side-text-right">
                        <TeamLabel name={teamB} tag={tagB} mode="full" />
                        {idB && <Link className="team-link small" to={`/team/${idB}`}>Team page &rarr;</Link>}
                      </div>
                      <LogoSlot src={logoB} name={teamB} tag={tagB} size={56} />
                    </div>
                  </div>
                  {lowDataTeams.length > 0 && (
                    <div className="match-hero-lowdata">
                      {lowDataTeams.map(t => <Chip variant="ghost" key={t.name}>LOW DATA</Chip>)}
                    </div>
                  )}
                  <PipBar pA={p} market={market} lowData={lowDataTeams.length > 0} />
                  {lowDataTeams.map(t => (
                    <p className="muted small" key={t.name}>{t.name} has {t.n} rated matches this season, so this rating moves fast.</p>
                  ))}
                  {!startPassed ? <p className="muted small">{COPY.modelBasis}</p> : (
                    <p className="muted small">PRE-MATCH: last model read before kick-off. {COPY.modelBasis}</p>
                  )}
                </>
              )}

              <div className="match-hero-stats">
                <StatCell label="Model" value={pct(favPct, 1)} tone="model" />
                <StatCell label="Market" value={market == null ? "\u2013" : pct(favourite === "a" ? market : 1 - market, 1)} tone={trusted ? "market" : undefined} />
                <StatCell label="Call" value={hit == null ? "\u2014" : hit ? "HIT" : "MISS"} tone={hit == null ? undefined : "result"} />
              </div>
              <div className="match-hero-gap">
                <GapChip model={p} market={market} spread={spread} favouredLabel={`${favourite === "a" ? (tagA ?? teamA) : (tagB ?? teamB)} FAVOURED`} />
                {hit === false && <Chip variant="market">UPSET</Chip>}
              </div>
              {hit === false && winnerTeam && winnerMarketPct != null && (
                <p className="muted small">{COPY.upset(favTeam, pct(favPct, 1), winnerTeam, pct(winnerMarketPct, 1))}</p>
              )}
              <p className="muted small">{COPY.marketBasis}</p>
            </div>
          </Panel>

          {f?.scores && f.best_of && (
            <section>
              <SectionHead title="Series score" />
              <ScoreForecast
                scores={f.scores} bestOf={f.best_of} teamA={teamA} teamB={teamB}
              />
            </section>
          )}

          {m && m.points.length > 0 && (
            <section>
              <SectionHead title="How the odds moved" right={<span className="muted small">{m.points.length} refreshes</span>} />
              <LineChart points={m.points} />
              <p className="muted small">Chance of {teamA} winning. Dots are refreshes of our forecast log, not a live price feed.</p>
              <details>
                <summary>All {m.points.length} snapshots</summary>
                <div className="scroll"><table>
                  <thead><tr><th>When</th><th className="n">Model</th><th className="n">Market</th><th className="n">Spread</th></tr></thead>
                  <tbody>{[...m.points].reverse().map(pt => (
                    <tr key={pt.observed_at}><td>{when(pt.observed_at)}</td><td className="n">{pct(pt.elo)}</td>
                      <td className="n">{pct(pt.market)}</td><td className="n">{pct(pt.spread)}</td></tr>
                  ))}</tbody>
                </table></div>
              </details>
            </section>
          )}
        </div>

        <div className="arena-grid-aside">
          {m?.recent_form && (
            <Panel cut="l" frame="line">
              <div className="pad">
                <SectionHead title="Recent form" />
                <p className="muted small">Last five played series known at the latest forecast refresh; excludes undated results, forfeits, draws and anonymous teams. Not an adjustment to the odds.</p>
                {([["a", teamA], ["b", teamB]] as const).map(([side, name]) => (
                  <div className="match-form-team" key={side}>
                    <div className="match-form-team-name ellipsis">{name}</div>
                    {m.recent_form[side].length ? (
                      <div className="match-form-rows">
                        {m.recent_form[side].map(row => (
                          <div className="match-form-row" key={row.match_id}>
                            <Chip variant={row.result === "W" ? "result" : "ghost"}>{row.result}</Chip>
                            <span className="ellipsis match-form-opp">vs {row.opponent}</span>
                            <span className="muted small num">{dayFmt(row.completed_at)}</span>
                          </div>
                        ))}
                      </div>
                    ) : <p className="muted small">No eligible played series in the recorded history.</p>}
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {m?.head_to_head && (
            <Panel cut="l" frame="line">
              <div className="pad">
                <SectionHead title="Head to head" />
                <HeadToHeadPanel h={m.head_to_head} teamA={teamA} teamB={teamB} />
              </div>
            </Panel>
          )}
        </div>
      </div>

      {m?.map_pool && (
        <section>
          <SectionHead title="Map history" />
          <p className="muted small">Each side&rsquo;s last 20 played Tier-1 maps with recorded scores before the latest forecast day. Historical results, not map-specific odds or likely veto picks; small samples can mislead.</p>
          <div className="match-maps-board">
            {([["a", teamA], ["b", teamB]] as const).map(([side, name]) => (
              <div key={side} className="match-maps-team">
                <div className="match-form-team-name ellipsis">{name}</div>
                {m.map_pool[side].length ? <div className="scroll"><table>
                  <thead><tr><th>Map</th><th className="n">W / played</th><th className="n">Win %</th><th className="n">Round share</th></tr></thead>
                  <tbody>{m.map_pool[side].map(row => (
                    <tr key={row.map}><td>{row.map}</td><td className="n">{row.won} / {row.played}</td>
                      <td className="n">{pct(row.won / row.played, 0)}</td><td className="n">{pct(row.round_share, 0)}</td></tr>
                  ))}</tbody>
                </table></div> : <p className="muted small">No scored Tier-1 maps in the recorded history.</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {f && <p className="small"><a href={f.url} target="_blank" rel="noreferrer">Match page on vlr.gg &#8599;</a></p>}
    </PageFade>
  );
}
