import { useMemo, useState } from "react";
import { useSnapshot } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import { Failure, Loading, PageHead } from "../components/ui";

export default function Matches() {
  const { data, error, loading } = useSnapshot();
  const [event, setEvent] = useState("all");
  const fixtures = useMemo(
    () => [...(data?.fixtures ?? [])].sort((a, b) => a.start.localeCompare(b.start)),
    [data],
  );
  if (loading) return <Loading />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const events = [...new Set(fixtures.map(f => f.event))];
  const shown = event === "all" ? fixtures : fixtures.filter(f => f.event === event);
  const byDay = new Map<string, typeof shown>();
  for (const f of shown) {
    const day = new Date(f.start).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    byDay.set(day, [...(byDay.get(day) ?? []), f]);
  }
  return (
    <>
      <PageHead eyebrow="Upcoming" title="Matches">
        Tap a match for the full breakdown. The blue dot is the model, orange is the market; both show the chance
        that the first-named team wins the series.
      </PageHead>
      {events.length > 1 && (
        <div className="filters">
          <button className={event === "all" ? "on" : ""} onClick={() => setEvent("all")}>All</button>
          {events.map(e => <button key={e} className={event === e ? "on" : ""} onClick={() => setEvent(e)}>{e}</button>)}
        </div>
      )}
      {shown.length === 0 && <p className="muted">No upcoming Tier-1 matches in the feed right now.</p>}
      {[...byDay].map(([day, list]) => (
        <section key={day}>
          <h2 className="day">{day}</h2>
          <div className="cards">{list.map(f => <FixtureCard key={f.match_id} f={f} />)}</div>
        </section>
      ))}
    </>
  );
}
