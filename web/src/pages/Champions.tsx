import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import PipBar from "../components/arena/PipBar";
import { Chip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import { useChampionsStatus } from "../lib/api";
import { LOW_DATA_MATCHES } from "../lib/constants";
import type { ChampionsGroup, ChampionsQualificationTeam } from "../lib/types";
import "./Champions.css";

const ORDER = ["opening_1", "opening_2", "winners", "elimination", "decider"] as const;
const LABELS = ["Opening 1", "Opening 2", "Winner's", "Elimination", "Decider"];

type TeamMeta = { tag: string | null; logo: string | null };

function utc(iso: string | null): string {
  if (!iso) return "an unknown time";
  const withZone = /[Zz]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  return `${new Date(withZone).toLocaleString(undefined, { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC`;
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

  return (
    <div className="champions-page">
      <header className="champ-head">
        <h1 className="champ-title">Group stage</h1>
        <p className="champ-lede">Recorded best-of-three results, confirmed advancement, and each team's chance to leave its group under the primary Elo forecast.</p>
      </header>
      <p className="champ-meta num">
        Canonical data last observed {utc(data.as_of)}; this is not a live event feed. Title odds wait for the playoff draw &mdash; unavailable until then.{" "}
        <a href="https://www.vlr.gg/event/2766/valorant-champions-2026" target="_blank" rel="noopener noreferrer">Check live schedule &#8599;</a>
      </p>

      <div className="champ-grid">
        {letters.map(letter => (
          <GroupPanel key={letter} letter={letter} group={data.groups[letter]} featured={letter === featuredLetter} teamMeta={teamMeta} />
        ))}
      </div>

      <section className="champ-note">
        <h2>Playoffs not drawn yet</h2>
        <p>The playoff draw is expected after October 4. Seeding and lower-bracket paths are not verified; title odds are unavailable. Group match results may lag the source.</p>
        <p>Group odds replay every remaining group series with the same win probability the fixture board shows for that pairing, holding ratings fixed until the group ends (real ratings move after each result). &ldquo;1st seed&rdquo; means winning the winners' match. Descriptive only: not a separate model and not betting advice.</p>
      </section>
    </div>
  );
}
