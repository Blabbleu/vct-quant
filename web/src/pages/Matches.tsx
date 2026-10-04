import { useMemo, useState } from "react";
import { useSnapshot } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import { LoadingBlocks, ErrorPanel, EmptyState } from "../components/arena/States";
import { COPY } from "../lib/constants";
import "./Matches.css";

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });

export default function Matches() {
  const { data, error, loading } = useSnapshot();
  const [event, setEvent] = useState("all");

  const fixtures = useMemo(
    () => [...(data?.fixtures ?? [])].sort((a, b) => a.start.localeCompare(b.start)),
    [data],
  );

  if (loading) return <LoadingBlocks label="Loading matches\u2026" />;
  if (error || !data) return <ErrorPanel detail={error ?? "no data"} onRetry={() => location.reload()} />;

  const events = [...new Set(fixtures.map(f => f.event))];
  const shown = event === "all" ? fixtures : fixtures.filter(f => f.event === event);

  const byDay = new Map<string, typeof shown>();
  for (const f of shown) {
    const day = dayFmt.format(new Date(f.start));
    byDay.set(day, [...(byDay.get(day) ?? []), f]);
  }

  return (
    <div className="matches-page">
      <header className="page-head">
        <h1>Matches</h1>
        <p className="lede">
          Upcoming Tier 1 matches grouped by day, in your local time. Red is the model, gold is the
          market; both show the chance that the first-named team wins the series.
        </p>
      </header>

      {events.length > 1 && (
        <div className="matches-filter">
          <label className="matches-filter-label" htmlFor="event-select">EVENT</label>
          <select id="event-select" value={event} onChange={e => setEvent(e.target.value)}>
            <option value="all">All Tier 1</option>
            {events.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState
          title={COPY.noMatchesScheduled}
          line={events[0] ? `Next known event: ${events[0]}.` : "No event is scheduled yet."}
          action={event !== "all" ? (
            <button type="button" className="btn btn-secondary" onClick={() => setEvent("all")}>
              Show all Tier 1
            </button>
          ) : undefined}
        />
      ) : (
        [...byDay].map(([day, list]) => (
          <section key={day} className="matches-day">
            <h2 className="matches-day-head">{day}</h2>
            <div className="arena-board matches-board">
              {list.map(f => <FixtureCard key={f.match_id} f={f} />)}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
