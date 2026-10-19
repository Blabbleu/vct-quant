import FixtureCard from "../FixtureCard";
import EventHero from "./EventHero";
import JustFinished from "./JustFinished";
import { BracketMini, ModelRecord, PowerRanks, RecentResults } from "./RailPanels";
import { EmptyState } from "../arena/States";
import { COPY } from "../../lib/constants";
import { fixtureTierCopy } from "../../lib/homeCopy";
import { eventContext, groupByDay, selectFixtures, stageParts, stageTimeline, isChampionsEvent } from "../../lib/matchesData";
import { PageFade, Stagger, StaggerItem } from "../../lib/motion";
import type { ChampionsStatus, ResultsList, Snapshot } from "../../lib/types";
import type { State } from "../../lib/swr";
import "../../pages/Matches.css";

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });
const dayLabel = (d: Date) => dayFmt.format(d);

type Async<T> = Pick<State<T>, "data" | "error" | "loading">;

export default function MatchesView({ data, results, champions, event, setEvent }: {
  data: Snapshot; results: Async<ResultsList>; champions: Async<ChampionsStatus>; event: string; setEvent: (event: string) => void;
}) {
  const fixtures = [...data.fixtures].sort((a, b) => a.start.localeCompare(b.start));
  const events = [...new Set(fixtures.map(f => f.event))];
  const selection = selectFixtures(fixtures, event);
  const shown = selection.fixtures;
  const selectedEvent = selection.event;
  const shownTierCopy = fixtureTierCopy(shown);
  const days = groupByDay(shown, dayLabel);
  const ctx = eventContext(shown, dayLabel);
  const isChampions = ctx != null && isChampionsEvent(ctx.event);
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

      {ctx && <EventHero ctx={ctx} fixtures={shown.filter(f => f.event === ctx.event)} timeline={timeline} timelineLoading={isChampions && champions.loading} />}

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
