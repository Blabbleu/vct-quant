import { Link } from "react-router-dom";
import { Failure, Loading, PageHead } from "../components/ui";
import { useChampionsStatus } from "../lib/api";
import type { ChampionsGroup } from "../lib/types";

const ORDER = ["opening_1", "opening_2", "winners", "elimination", "decider"] as const;
const LABELS = ["Opening 1", "Opening 2", "Winner's", "Elimination", "Decider"];

function Team({ id, group }: { id: number; group: ChampionsGroup }) {
  return <Link to={`/team/${id}`} title={`Exact vlr.gg team ID ${id}`}>{group.entrants[String(id)] ?? `Team ${id}`}</Link>;
}

function Group({ letter, group }: { letter: string; group: ChampionsGroup }) {
  return <section className="panel pad champions-group" aria-label={`Group ${letter}`}>
    <div className="head"><h2>Group {letter}</h2><span className="chip">{group.qualifiers.length} / 2 qualified</span></div>
    {group.unverified_match_ids.length > 0 && <p className="champions-warning" role="status">
      Unverified completed source rows: {group.unverified_match_ids.join(", ")}. Advancement is withheld until verified.
    </p>}
    <div className="champions-slots">
      {ORDER.map((key, index) => {
        const slot = group.slots[key];
        const result = group.results[key];
        const participants = result?.team_ids ?? group.expected[key] ?? slot.team_ids;
        const flagged = group.unverified_match_ids.includes(slot.match_id);
        return <div className="champions-slot" key={slot.match_id}>
          <div className="head"><b className="small">{LABELS[index]}</b><a className="small num" href={`https://www.vlr.gg/${slot.match_id}`} target="_blank" rel="noopener noreferrer">Source #{slot.match_id} ↗</a></div>
          <div className="champions-sides">
            {flagged ? <span className="muted small">Result unverified</span> : participants ? participants.map((id, side) =>
              <div className="champions-side" key={id}>
                <Team id={id} group={group} />
                {result && <b className="num" aria-label={`${result.scores[side]} maps`}>{result.scores[side]}</b>}
              </div>) : <span className="muted small">Awaiting earlier results</span>}
          </div>
          {result && !flagged && <span className="muted small">Verified recorded result</span>}
        </div>;
      })}
    </div>
    <div className="champions-qualified small"><b>Confirmed qualifiers:</b> {group.qualifiers.length ? group.qualifiers.map((id, i) =>
      <span key={id}>{i > 0 && ", "}<Team id={id} group={group} /></span>) : <span className="muted">None yet</span>}</div>
  </section>;
}

export default function Champions() {
  const { data, error, loading } = useChampionsStatus();
  if (loading) return <Loading what="Champions group results" />;
  if (error || !data) return <Failure error={error ?? "Champions group status unavailable"} />;
  return <>
    <PageHead eyebrow="Champions Shanghai · 2026" title="Group stage">
      Recorded best-of-three results and confirmed group advancement only. No simulated bracket or title odds.
    </PageHead>
    <p className="muted small">Canonical data last observed {data.as_of ? new Date(/[Zz]|[+-]\d\d:\d\d$/.test(data.as_of) ? data.as_of : data.as_of + "Z").toLocaleString(undefined, { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" }) + " UTC" : "at an unknown time"}; this is not a live event feed. <a href="https://www.vlr.gg/event/2766/valorant-champions-2026" target="_blank" rel="noopener noreferrer">Check live schedule ↗</a></p>
    <div className="champions-grid">{(["A", "B", "C", "D"] as const).map(letter => <Group key={letter} letter={letter} group={data.groups[letter]} />)}</div>
    <section className="panel pad prose">
      <h2>Playoffs not drawn yet</h2>
      <p>The playoff draw is expected after October 4. Seeding and lower-bracket paths are not verified; title odds are unavailable. Group match results may lag the source.</p>
    </section>
  </>;
}
