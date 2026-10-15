import { useMemo, useState } from "react";
import { useChampionsStatus, useResults, useSnapshot } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import EventHero from "../components/matches/EventHero";
import JustFinished from "../components/matches/JustFinished";
import { BracketMini, ModelRecord, PowerRanks, RecentResults } from "../components/matches/RailPanels";
import { LoadingBlocks, ErrorPanel, EmptyState } from "../components/arena/States";
import { COPY } from "../lib/constants";
import { fixtureTierCopy } from "../lib/homeCopy";
import { eventContext, groupByDay, selectFixtures, stageParts, stageTimeline } from "../lib/matchesData";
import { PageFade, Stagger, StaggerItem } from "../lib/motion";
import "./Matches.css";

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });
const dayLabel = (d: Date) => dayFmt.format(d);

export default function Matches() {
  const { data, error, loading } = useSnapshot();
  const results = useResults();
  const champions = useChampionsStatus();
  const [event, setEvent] = useState("all");

  const fixtures = useMemo(
    () => [...(data?.fixtures ?? [])].sort((a, b) => a.start.localeCompare(b.start)),
    [data],
  );

  if (loading) return <LoadingBlocks label="Loading matches\u2026" />;
  if (error || !data) return <ErrorPanel detail={error ?? "no data"} onRetry={() => location.reload()} />;

  const events = [...new Set(fixtures.map(f => f.event))];
  const selection = selectFixtures(fixtures, event);
  const shown = selection.fixtures;
  const selectedEvent = selection.event;
  const shownTierCopy = fixtureTierCopy(shown);
  const days = groupByDay(shown, dayLabel);
  const ctx = eventContext(shown, dayLabel);
  const isChampions = ctx != null && /champions/i.test(ctx.event);
  const timeline = isChampions ? stageTimeline(champions.data?.playoffs, ctx.next.series) : [];
  const playoffs = champions.data?.playoffs;

  return (
    <PageFade className="matches-page">
      <header className="page-head">
        <h1>Matches</h1>
        <p className="lede">
          {shown.length === 0
            ? "No upcoming matches are currently scheduled."
            : <>Upcoming {shownTierCopy} matches grouped by day, in your local time. Red is the model, gold is the market; both show the chance that the first-named team wins the series.</>}
        </p>
      </header>

      {ctx && <EventHero ctx={ctx} timeline={timeline} timelineLoading={isChampions && champions.loading} />}

      {events.length > 1 && (
        <div className="matches-filter">
          <label className="matches-filter-label" htmlFor="event-select">EVENT</label>
          <select id="event-select" value={selectedEvent} onChange={e => setEvent(e.target.value)}>
            <option value="all">All {fixtureTierCopy(fixtures)}</option>
            {events.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
      )}

      <div className="matches-layout">
        <div className="matches-main">
          {shown.length === 0 ? (
            <EmptyState
              title={COPY.noMatchesScheduled}
              line={events[0] ? `Next known event: ${events[0]}.` : "No event is scheduled yet."}
              action={selectedEvent !== "all" ? (
                <button type="button" className="btn btn-secondary" onClick={() => setEvent("all")}>
                  Show all {fixtureTierCopy(fixtures)}
                </button>
              ) : undefined}
            />
          ) : (
            days.map(day => {
              const stages = [...new Set(day.items.map(f => stageParts(f.series).stage).filter(Boolean))];
              return (
                <section key={day.key} className="matches-day">
                  <h2 className="matches-day-head">
                    <span>{day.label}</span>
                    <span className="matches-day-meta num">
                      {stages.join(" / ")}{stages.length > 0 ? " \u00B7 " : ""}{day.items.length} {day.items.length === 1 ? "match" : "matches"}
                    </span>
                  </h2>
                  <Stagger className="matches-board" key={`${selectedEvent}-${day.key}`}>
                    {day.items.map(f => <StaggerItem key={f.match_id} className="stagger-cell"><FixtureCard f={f} /></StaggerItem>)}
                  </Stagger>
                </section>
              );
            })
          )}

          <JustFinished results={results} />
        </div>

        <aside className="matches-rail" aria-label="Context">
          <ModelRecord results={results} index={0} />
          <RecentResults results={results} index={1} />
          {isChampions && <BracketMini playoffs={playoffs} loading={champions.loading} index={2} />}
          <PowerRanks rankings={data.rankings} index={3} />
        </aside>
      </div>
    </PageFade>
  );
}
