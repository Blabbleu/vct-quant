import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import PipBar from "../components/arena/PipBar";
import { Chip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import SectionHead from "../components/arena/SectionHead";
import GapChip from "../components/arena/GapChip";
import Bracket3DSection from "../components/bracket3d/Bracket3DSection";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import { useChampionsStatus } from "../lib/api";
import { LOW_DATA_MATCHES } from "../lib/constants";
import { utc, utcShort } from "../lib/format";
import type { ChampionsGroup, ChampionsPlayoffMatch, ChampionsPlayoffs, ChampionsQualificationTeam } from "../lib/types";
import "./Champions.css";

const ORDER = ["opening_1", "opening_2", "winners", "elimination", "decider"] as const;
const LABELS = ["Opening 1", "Opening 2", "Winner's", "Elimination", "Decider"];

type TeamMeta = { tag: string | null; logo: string | null };

const pct1 = (p: number) => (p * 100).toFixed(1);

/** One verified Upper Quarterfinal: kick-off, both sides with model %, and the market read (or none). */
function PlayoffMatch({ m }: { m: ChampionsPlayoffMatch }) {
  const [a, b] = m.sides;
  const forecast = a.p_win != null && b.p_win != null;
  const lowData = (s: typeof a) => s.matches != null && s.matches < LOW_DATA_MATCHES;
  const favTag = forecast ? (a.p_win! >= 0.5 ? (a.tag ?? a.name) : (b.tag ?? b.name)).toUpperCase() : "";
  const sideEl = (s: typeof a, right: boolean) => (
    <div className={`champ-po-side${right ? " champ-po-side-right" : ""}`}>
      <LogoSlot src={s.logo} name={s.name} tag={s.tag} size={34} />
      <Link to={`/team/${s.team_id}`} className="champ-team-link"><TeamLabel name={s.name} tag={s.tag} mode="auto" /></Link>
      {lowData(s) && <Chip variant="ghost">LOW DATA</Chip>}
    </div>
  );
  const pct = (s: typeof a, fav: boolean) => (
    <span className={`num champ-po-pct${fav ? " champ-po-pct-fav" : " champ-po-pct-dim"}`}>
      {s.p_win != null ? pct1(s.p_win) : "--.-"}
    </span>
  );
  return (
    <Panel cut="l" frame="line" className="champ-po-card">
      <div className="champ-po-in">
        <div className="champ-po-top">
          <span className="num champ-po-time">{utcShort(m.start)}</span>
          <span className="muted small num ellipsis">
            {m.stage}{m.best_of ? ` \u00B7 Bo${m.best_of}` : ""}
          </span>
        </div>
        <div className="champ-po-teams">
          {sideEl(a, false)}
          {pct(a, forecast && a.p_win! >= 0.5)}
          <span className="vs">vs</span>
          {pct(b, forecast && b.p_win! > 0.5)}
          {sideEl(b, true)}
        </div>
        {forecast ? <PipBar pA={a.p_win!} market={m.market?.p_a ?? null} lowData={lowData(a) || lowData(b)} blocks={20} /> : null}
        <div className="champ-po-bottom">
          {forecast
            ? <GapChip model={a.p_win!} market={m.market?.p_a ?? null} spread={m.market?.spread ?? null} favouredLabel={`${favTag} FAVOURED`} />
            : <span className="champ-ph-line num">Forecast unavailable</span>}
          {m.url && <a className="small" href={m.url} target="_blank" rel="noopener noreferrer">VLR &#8599;</a>}
        </div>
      </div>
    </Panel>
  );
}

function PlayoffsSection({ playoffs }: { playoffs: ChampionsPlayoffs }) {
  return (
    <section className="champ-playoffs">
      <SectionHead title="Upper Quarterfinals" right={<Chip variant="ghost">DRAWN &middot; ROUTING TBD</Chip>} />
      <p className="champ-sub">
        The four opening matchups, as published on Riot's bracket and corroborated on VLR (observed {utc(playoffs.observed_at)}).
        Win % is the primary Elo forecast for each series; market shows only where a Polymarket price exists.
      </p>
      <div className="champ-po-grid">
        {[...playoffs.opening]
          .sort((x, y) => (x.start ?? "9").localeCompare(y.start ?? "9") || x.match_id - y.match_id)
          .map(m => <PlayoffMatch key={m.match_id} m={m} />)}
      </div>
      {playoffs.schedule.length > 0 && (
        <Panel cut="m" frame="line" className="champ-po-sched">
          <div className="champ-po-sched-in">
            <div className="champ-results-head">Later rounds &middot; teams TBD</div>
            <ul className="champ-po-sched-list">
              {playoffs.schedule.map(r => (
                <li key={r.match_id}>
                  <span className="champ-po-sched-stage">{r.stage}</span>
                  <span className="num champ-po-sched-when">{utcShort(r.start)}{r.best_of ? ` \u00B7 Bo${r.best_of}` : ""}</span>
                  <span className="champ-ph-line num">[ TBD ]</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      )}
    </section>
  );
}

/** One entrant row: logo, name/tag, chips, playoff % and a compact pip bar beneath. */
function TeamRow({ id, group, q, meta }: {
  id: number; group: ChampionsGroup; q: ChampionsQualificationTeam | undefined; meta: TeamMeta | undefined;
}) {
  const name = group.entrants[String(id)] ?? `Team ${id}`;
  const lowData = q != null && q.rated_matches < LOW_DATA_MATCHES;
  return (
    <div className="champ-team-row">
      <LogoSlot src={meta?.logo} name={name} tag={meta?.tag} size={34} />
      <div className="champ-team-id">
        <Link to={`/team/${id}`} className="champ-team-link">
          <TeamLabel name={name} tag={meta?.tag} mode="auto" />
        </Link>
        <div className="champ-team-chips">
          {q?.qualified && <Chip variant="result">QUALIFIED</Chip>}
          {lowData && <Chip variant="ghost">LOW DATA</Chip>}
        </div>
      </div>
      {q ? (
        <div className="champ-team-pct num" title={`1st seed chance ${(q.p_first * 100).toFixed(1)}%`}>
          {(q.p_qualify * 100).toFixed(1)}
        </div>
      ) : <div className="champ-team-pct num champ-ph">--.-</div>}
      <div className="champ-team-bar">
        {q ? <PipBar pA={q.p_qualify} blocks={10} lowData={lowData} /> : <PipBar pA={0} blocks={10} lowData />}
      </div>
    </div>
  );
}

/** A played, awaiting or not-yet-seeded slot, shown as a compact score bug. */
function SlotBug({ slot, group, teamMeta }: {
  slot: (typeof ORDER)[number]; group: ChampionsGroup; teamMeta: Record<number, TeamMeta>;
}) {
  const info = group.slots[slot];
  const result = group.results[slot];
  const flagged = group.unverified_match_ids.includes(info.match_id);
  const participants = result?.team_ids ?? group.expected[slot] ?? info.team_ids;
  const label = LABELS[ORDER.indexOf(slot)];

  if (flagged) {
    return (
      <div className="champ-bug cut-m champ-bug-ph">
        <span className="champ-bug-label">{label}</span>
        <span className="champ-bug-ph-text">RESULT UNVERIFIED</span>
      </div>
    );
  }
  if (result && participants) {
    const [idA, idB] = participants;
    const [sA, sB] = result.scores;
    const aWins = sA > sB;
    const nameA = group.entrants[String(idA)] ?? `Team ${idA}`;
    const nameB = group.entrants[String(idB)] ?? `Team ${idB}`;
    return (
      <div className="champ-bug cut-m champ-bug-played">
        <span className="champ-bug-label">{label}</span>
        <div className="champ-bug-score">
          <span className={`champ-bug-side${aWins ? " champ-bug-win" : ""}`}>
            <LogoSlot src={teamMeta[idA]?.logo} name={nameA} tag={teamMeta[idA]?.tag} size={20} faded={!aWins} />
            <TeamLabel name={nameA} tag={teamMeta[idA]?.tag} />
          </span>
          <span className="champ-bug-num num">{sA}&#8211;{sB}</span>
          <span className={`champ-bug-side champ-bug-side-right${!aWins ? " champ-bug-win" : ""}`}>
            <TeamLabel name={nameB} tag={teamMeta[idB]?.tag} />
            <LogoSlot src={teamMeta[idB]?.logo} name={nameB} tag={teamMeta[idB]?.tag} size={20} faded={aWins} />
          </span>
        </div>
      </div>
    );
  }
  if (participants) {
    const [idA, idB] = participants;
    const nameA = group.entrants[String(idA)] ?? `Team ${idA}`;
    const nameB = group.entrants[String(idB)] ?? `Team ${idB}`;
    return (
      <div className="champ-bug cut-m champ-bug-ph">
        <span className="champ-bug-label">{label}</span>
        <span className="champ-bug-ph-text">{nameA} vs {nameB} &middot; awaiting result</span>
      </div>
    );
  }
  return (
    <div className="champ-bug cut-m champ-bug-ph">
      <span className="champ-bug-label">{label}</span>
      <span className="champ-bug-ph-text">[ TBD ]</span>
    </div>
  );
}

function GroupPanel({ letter, group, featured, teamMeta }: {
  letter: string; group: ChampionsGroup; featured: boolean; teamMeta: Record<number, TeamMeta>;
}) {
  const q = group.qualification;
  const byId = new Map<number, ChampionsQualificationTeam>();
  if (q && "teams" in q) for (const t of q.teams) byId.set(t.team_id, t);
  const ids = Object.keys(group.entrants).map(Number);
  const sortedIds = q && "teams" in q
    ? [...ids].sort((a, b) => (byId.get(b)?.p_qualify ?? 0) - (byId.get(a)?.p_qualify ?? 0))
    : ids;

  return (
    <Panel cut="l" frame="line" brackets={featured} className="champ-group">
      <div className="champ-group-in">
        <div className="champ-group-head">
          <h2>Group {letter}</h2>
          <span className="champ-group-count num">{group.qualifiers.length} / 2 QUALIFIED</span>
        </div>
        {group.unverified_match_ids.length > 0 && (
          <p className="champ-warning">
            Unverified source rows: {group.unverified_match_ids.join(", ")}. Advancement withheld until verified.
          </p>
        )}
        <div className="champ-teams">
          {sortedIds.map(id => <TeamRow key={id} id={id} group={group} q={byId.get(id)} meta={teamMeta[id]} />)}
        </div>
        {q && !("teams" in q) && <p className="champ-ph-line">Qualification odds withheld: {q.withheld}.</p>}

        <div className="champ-results-head">Results so far</div>
        <div className="champ-bugs">
          {ORDER.map(key => <SlotBug key={key} slot={key} group={group} teamMeta={teamMeta} />)}
        </div>

        <div className="champ-qualified">
          <span className="champ-qualified-label">Confirmed qualifiers</span>
          {group.qualifiers.length
            ? <span>{group.qualifiers.map((id, i) => (
                <span key={id}>{i > 0 && ", "}<Link to={`/team/${id}`}>{group.entrants[String(id)] ?? `Team ${id}`}</Link></span>
              ))}</span>
            : <span className="champ-ph-line">None yet</span>}
        </div>
      </div>
    </Panel>
  );
}

export default function Champions() {
  const { data, error, loading } = useChampionsStatus();
  const [teamMeta, setTeamMeta] = useState<Record<number, TeamMeta>>({});

  useEffect(() => {
    if (!data) return;
    const ids = new Set<number>();
    for (const g of Object.values(data.groups)) {
      for (const id of Object.keys(g.entrants)) ids.add(Number(id));
    }
    const missing = [...ids].filter(id => !(id in teamMeta));
    if (missing.length === 0) return;
    let alive = true;
    Promise.all(missing.map(id =>
      fetch(`/api/team/${id}`).then(r => r.ok ? r.json() : null).then(t => [id, t] as const).catch(() => [id, null] as const),
    )).then(results => {
      if (!alive) return;
      setTeamMeta(prev => {
        const next = { ...prev };
        for (const [id, t] of results) next[id] = { tag: t?.tag ?? null, logo: t?.logo ?? null };
        return next;
      });
    });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (loading) return <div className="champions-page"><LoadingBlocks label="Loading Champions group results\u2026" /></div>;
  if (error || !data) return <div className="champions-page"><ErrorPanel detail={error ?? "Champions group status unavailable"} onRetry={() => location.reload()} /></div>;

  const letters = ["A", "B", "C", "D"] as const;
  const featuredLetter = letters.reduce((best, l) => {
    const n = Object.keys(data.groups[l].results).length;
    const bestN = Object.keys(data.groups[best].results).length;
    return n > bestN ? l : best;
  }, letters[0]);

  const playoffs = data.playoffs && data.playoffs.opening.length > 0 ? data.playoffs : null;
  const groupsDone = letters.every(l => data.groups[l].qualifiers.length === 2 && data.groups[l].unverified_match_ids.length === 0);

  return (
    <div className="champions-page">
      <header className="champ-head">
        <h1 className="champ-title">{playoffs ? "Playoffs" : "Group stage"}</h1>
        <p className="champ-lede">
          {playoffs
            ? "The opening Upper Quarterfinals are drawn, with the primary Elo forecast for each series. Later rounds are not yet verified, so they stay TBD."
            : "Recorded best-of-three results, confirmed advancement, and each team's chance to leave its group under the primary Elo forecast."}
        </p>
      </header>
      <p className="champ-meta num">
        Canonical data last observed {utc(data.as_of)}; this is not a live event feed.{" "}
        {playoffs
          ? "Title odds are unavailable until the full bracket routing (upper/lower edges and grand-final rules) is verified."
          : "Title odds wait for the playoff draw \u2014 unavailable until then."}{" "}
        <a href="https://www.vlr.gg/event/2766/valorant-champions-2026" target="_blank" rel="noopener noreferrer">Check live schedule &#8599;</a>
      </p>

      {playoffs && <Bracket3DSection playoffs={playoffs} />}
      {playoffs && <PlayoffsSection playoffs={playoffs} />}

      {playoffs && (
        <SectionHead
          title={groupsDone ? "Group stage (complete)" : "Group stage"}
          right={<Chip variant="ghost">{groupsDone ? "8 / 8 QUALIFIED" : "IN PROGRESS"}</Chip>}
        />
      )}
      <div className="champ-grid">
        {letters.map(letter => (
          <GroupPanel key={letter} letter={letter} group={data.groups[letter]} featured={!playoffs && letter === featuredLetter} teamMeta={teamMeta} />
        ))}
      </div>

      <section className="champ-note">
        {!playoffs && (
          <>
            <h2>Playoffs not drawn yet</h2>
            <p>The playoff draw is expected after October 4. Seeding and lower-bracket paths are not verified; title odds are unavailable. Group match results may lag the source.</p>
          </>
        )}
        {playoffs && <p>Only the four opening pairings and the published schedule are verified. Upper/lower-bracket routing and grand-final rules are not, so no title odds are shown. Group match results may lag the source.</p>}
        <p>Group odds replay every remaining group series with the same win probability the fixture board shows for that pairing, holding ratings fixed until the group ends (real ratings move after each result). &ldquo;1st seed&rdquo; means winning the winners' match. Descriptive only: not a separate model and not betting advice.</p>
      </section>
    </div>
  );
}
