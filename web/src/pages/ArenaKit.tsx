import { useEffect, useState } from "react";
import type { Fixture, Ranking } from "../lib/types";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import PipBar from "../components/arena/PipBar";
import GapChip from "../components/arena/GapChip";
import { Chip, CountdownChip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import SectionHead from "../components/arena/SectionHead";
import StatCell from "../components/arena/StatCell";
import Banner from "../components/arena/Banner";
import { LoadingBlocks, ErrorPanel, EmptyState, StaleNote } from "../components/arena/States";
import RecordBar from "../components/arena/RecordBar";
import { COPY } from "../lib/constants";
import { eloWinProbability } from "../lib/format";

/**
 * Dev-only style guide: every Terminal Arena component in its variants, fed
 * with real teams/fixtures/rankings from the live API. Not linked from the
 * nav; visit /arena directly. Page agents use this as the reference for the
 * exact class names and props to build real pages against.
 */
export default function ArenaKit() {
  const [fixtures, setFixtures] = useState<Fixture[] | null>(null);
  const [rankings, setRankings] = useState<Ranking[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/fixtures").then(r => r.json()),
      fetch("/api/rankings").then(r => r.json()),
    ]).then(([f, r]) => { setFixtures(f); setRankings(r.rankings); }).catch(e => setErr(String(e)));
  }, []);

  if (err) return <ErrorPanel detail={err} onRetry={() => location.reload()} />;
  if (!fixtures || !rankings) return <LoadingBlocks />;

  const byTag = (tag: string) => rankings.find(r => r.tag === tag);
  const byName = (name: string) => rankings.find(r => r.team === name);
  const the100t = byTag("100T")!;
  const t1 = byName("T1")!;
  const nrg = byTag("NRG")!; // 9 matches this season -> LOW DATA
  const megaMinors = byName("Mega Minors")!; // no tag -> initials MM
  const prx = byTag("PRX")!;
  const wideSpreadFixture = fixtures.find(f => f.team_b === "EDward Gaming")!; // GE vs EDG, spread .39
  const marketFixture = fixtures.find(f => f.market != null && f.team_a === "100 Thieves") ?? fixtures[0];
  // EDG isn't in the Tier-1 rankings sample; it shows up in fixtures (GE vs EDG). Use that for the dark-logo check.
  const edgFixture = fixtures.find(f => f.tag_b === "EDG")!;
  const p100tVsT1 = eloWinProbability(the100t.elo, t1.elo); // 100T vs T1, computed from real ratings, no market attached

  return (
    <div className="arena-kit">
      <header className="page-head">
        <h1>Arena kit</h1>
        <p className="lede">Dev-only style guide. Every Terminal Arena component, real data. Not linked from the nav.</p>
      </header>

      <section className="arena-kit-section">
        <SectionHead title="Logo slot" right={<span className="muted small">Dark-logo auto-detect</span>} />
        <div className="arena-kit-row">
          {[20, 34, 56].map(size => (
            <div className="arena-kit-sample" key={size}>
              <div className="arena-kit-sample-label">{size}px</div>
              <LogoSlot src={the100t.logo} name={the100t.team} tag={the100t.tag} size={size as 20 | 34 | 56} />
            </div>
          ))}
          <div className="arena-kit-sample">
            <div className="arena-kit-sample-label">EDG (dark logo check)</div>
            <LogoSlot src={edgFixture.logo_b} name={edgFixture.team_b} tag={edgFixture.tag_b} size={56} />
          </div>
          <div className="arena-kit-sample">
            <div className="arena-kit-sample-label">Paper Rex (dark logo check)</div>
            <LogoSlot src={prx.logo} name={prx.team} tag={prx.tag} size={56} />
          </div>
          <div className="arena-kit-sample">
            <div className="arena-kit-sample-label">Losing side (faded)</div>
            <LogoSlot src={t1.logo} name={t1.team} tag={t1.tag} size={56} faded />
          </div>
          <div className="arena-kit-sample">
            <div className="arena-kit-sample-label">No logo, no tag (Mega Minors → MM)</div>
            <LogoSlot src={megaMinors.logo} name={megaMinors.team} tag={megaMinors.tag} size={56} />
          </div>
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Team label" />
        <div className="arena-kit-row">
          <TeamLabel name={prx.team} tag={prx.tag} mode="tag" />
          <TeamLabel name={t1.team} tag={t1.tag} mode="tag" />
          <TeamLabel name="Nongshim RedForce" tag="NS" mode="tag" />
          <span style={{ maxWidth: 120 }}><TeamLabel name="Nongshim RedForce" tag="NS" mode="full" /></span>
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Pip bar" />
        <div className="arena-kit-row" style={{ flexDirection: "column", width: "100%" }}>
          <div className="arena-kit-sample" style={{ width: "100%" }}>
            <div className="arena-kit-sample-label">{the100t.tag} vs T1, {(p100tVsT1 * 100).toFixed(1)}% · no market</div>
            <PipBar pA={p100tVsT1} />
          </div>
          <div className="arena-kit-sample" style={{ width: "100%" }}>
            <div className="arena-kit-sample-label">With market notch ({marketFixture.team_a} vs {marketFixture.team_b})</div>
            <PipBar pA={marketFixture.p_a} market={marketFixture.market} />
          </div>
          <div className="arena-kit-sample" style={{ width: "100%" }}>
            <div className="arena-kit-sample-label">Low data (NRG, {nrg.matches} matches) — outline blocks</div>
            <PipBar pA={0.5} lowData />
          </div>
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Gap chip" />
        <div className="arena-kit-row" style={{ flexDirection: "column", alignItems: "flex-start" }}>
          <GapChip model={0.505} market={0.5} />
          <GapChip model={0.588} market={0.5} />
          <GapChip model={0.72} market={0.56} />
          <GapChip model={p100tVsT1} market={null} favouredLabel={`${the100t.tag} FAVOURED`} />
          <GapChip model={wideSpreadFixture.p_a} market={wideSpreadFixture.market} spread={wideSpreadFixture.spread} />
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Chip / Countdown" />
        <div className="arena-kit-row">
          <Chip variant="default">DEFAULT</Chip>
          <Chip variant="model">MODEL</Chip>
          <Chip variant="market">MARKET</Chip>
          <Chip variant="result">WIN</Chip>
          <Chip variant="ghost">LOW DATA</Chip>
          <CountdownChip iso={marketFixture.start} />
          <CountdownChip iso={new Date(Date.now() + 3 * 86400000).toISOString()} />
          <CountdownChip iso={new Date(Date.now() - 60000).toISOString()} />
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Panel" />
        <div className="arena-kit-row">
          <Panel cut="l" frame="line" className="arena-kit-sample">
            <div className="pad">cut-l, line frame</div>
          </Panel>
          <Panel cut="m" frame="result" className="arena-kit-sample">
            <div className="pad">cut-m, result frame</div>
          </Panel>
          <Panel cut="l" frame="line" brackets className="arena-kit-sample">
            <div className="pad">cut-l, corner brackets (gap panel)</div>
          </Panel>
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Stat cell" />
        <div className="arena-kit-row">
          <StatCell label="Model" value="53.5" tone="model" />
          <StatCell label="Market" value="50.0" tone="market" />
          <StatCell label="Call" value="HIT" tone="result" />
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Banner" />
        <div className="arena-kit-row" style={{ flexDirection: "column", alignItems: "flex-start" }}>
          <Banner kind="complete" text="MATCH COMPLETE" />
          <Banner kind="live" text="LIVE" />
          <Banner kind="upcoming" text={`KICK-OFF 09:00 · T${String.fromCharCode(0x2212)}14H`} />
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="States" />
        <div className="arena-kit-row" style={{ flexDirection: "column", width: "100%", alignItems: "stretch" }}>
          <LoadingBlocks rows={2} />
          <ErrorPanel lastGood="14:02" onRetry={() => {}} />
          <EmptyState title={COPY.noMatchesScheduled} line="Next known event: Valorant Champions 2026, Oct 2." action={<button type="button" className="btn btn-secondary">Show all Tier 1</button>} />
          <StaleNote asOf="14:02" />
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Record bar" />
        <RecordBar calls={6} hits={4} logLoss={0.6} market={0.55} />
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Buttons and select" />
        <div className="arena-kit-row">
          <button type="button" className="btn btn-primary">Primary</button>
          <button type="button" className="btn btn-secondary">Secondary</button>
          <select defaultValue="all"><option value="all">All Tier 1</option><option value="t2">Tier 2</option></select>
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Layout: matches board (.arena-board)" right={<span className="muted small">1 col &lt;768 · 2 cols 768–1199 · 3 cols &ge;1200</span>} />
        <div className="arena-board">
          {fixtures.slice(0, 6).map(f => (
            <Panel cut="l" frame="line" key={f.match_id}>
              <div className="pad" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="arena-kit-row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <CountdownChip iso={f.start} />
                  <span className="muted small ellipsis">{f.series}</span>
                </div>
                <div className="arena-kit-row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <span className="arena-kit-row" style={{ gap: 8 }}>
                    <LogoSlot src={f.logo_a} name={f.team_a} tag={f.tag_a} size={34} />
                    <TeamLabel name={f.team_a} tag={f.tag_a} />
                  </span>
                  <span className="num" style={{ fontWeight: 800 }}>{(f.p_a * 100).toFixed(1)}</span>
                  <span className="vs">vs</span>
                  <span className="num" style={{ fontWeight: 800 }}>{((1 - f.p_a) * 100).toFixed(1)}</span>
                  <span className="arena-kit-row" style={{ gap: 8 }}>
                    <TeamLabel name={f.team_b} tag={f.tag_b} />
                    <LogoSlot src={f.logo_b} name={f.team_b} tag={f.tag_b} size={34} />
                  </span>
                </div>
                <PipBar pA={f.p_a} market={f.market} />
                <GapChip model={f.p_a} market={f.market} spread={f.spread} favouredLabel={`${f.p_a >= 0.5 ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)} FAVOURED`} />
              </div>
            </Panel>
          ))}
        </div>
      </section>

      <section className="arena-kit-section">
        <SectionHead title="Layout: match hero + aside (.arena-grid)" right={<span className="muted small">Stacked &lt;1200 · 8/4 split &ge;1200</span>} />
        <div className="arena-grid">
          <div className="arena-grid-main">
            <Panel cut="l" frame="line" brackets>
              <div className="pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <Banner kind="upcoming" text={`KICK-OFF · ${new Date(marketFixture.start).toLocaleString()}`} />
                <div className="arena-kit-row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <span className="arena-kit-row" style={{ gap: 12 }}>
                    <LogoSlot src={marketFixture.logo_a} name={marketFixture.team_a} tag={marketFixture.tag_a} size={56} />
                    <TeamLabel name={marketFixture.team_a} tag={marketFixture.tag_a} mode="full" />
                  </span>
                  <span className="num" style={{ fontSize: 26, fontWeight: 800 }}>{(marketFixture.p_a * 100).toFixed(1)}</span>
                  <span className="vs">vs</span>
                  <span className="num" style={{ fontSize: 26, fontWeight: 800 }}>{((1 - marketFixture.p_a) * 100).toFixed(1)}</span>
                  <span className="arena-kit-row" style={{ gap: 12 }}>
                    <TeamLabel name={marketFixture.team_b} tag={marketFixture.tag_b} mode="full" />
                    <LogoSlot src={marketFixture.logo_b} name={marketFixture.team_b} tag={marketFixture.tag_b} size={56} />
                  </span>
                </div>
                <PipBar pA={marketFixture.p_a} market={marketFixture.market} />
                <div className="arena-kit-row">
                  <StatCell label="Model" value={(marketFixture.p_a * 100).toFixed(1)} tone="model" />
                  <StatCell label="Market" value={marketFixture.market != null ? (marketFixture.market * 100).toFixed(1) : String.fromCharCode(0x2013)} tone="market" />
                  <StatCell label="Call" value={String.fromCharCode(0x2014)} />
                </div>
                <p className="muted small">{COPY.modelBasis}</p>
              </div>
            </Panel>
          </div>
          <div className="arena-grid-aside">
            <Panel cut="m" frame="line">
              <div className="pad" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <SectionHead title="Record" />
                <RecordBar calls={6} hits={4} logLoss={0.6} market={0.55} />
              </div>
            </Panel>
          </div>
        </div>
      </section>

      <p className="muted small">{COPY.modelBasis} {COPY.marketBasis} {COPY.edgeDisclaimer}</p>
    </div>
  );
}
