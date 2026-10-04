import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useChampionsStatus, useResults, useSnapshot } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import EventHero from "../components/matches/EventHero";
import FinishedCard from "../components/matches/FinishedCard";
import { BracketMini, ModelRecord, PowerRanks, RecentResults } from "../components/matches/RailPanels";
import SectionHead from "../components/arena/SectionHead";
import { LoadingBlocks, ErrorPanel, EmptyState } from "../components/arena/States";
import { COPY } from "../lib/constants";
import { eventContext, groupByDay, justFinished, stageParts, stageTimeline } from "../lib/matchesData";
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
  const shown = event === "all" ? fixtures : fixtures.filter(f => f.event === event);
  const days = groupByDay(shown, dayLabel);
  const ctx = eventContext(shown, dayLabel);
  const isChampions = ctx != null && /champions/i.test(ctx.event);
  const timeline = isChampions ? stageTimeline(champions.data?.playoffs, ctx.next.series) : [];
  const finished = results.data ? justFinished(results.data.rows, { hours: 48, min: 6, max: 8 }) : [];
  const playoffs = champions.data?.playoffs;

  return (
    <PageFade className="matches-page">
      <header className="page-head">
        <h1>Matches</h1>
        <p className="lede">
          Upcoming Tier 1 matches grouped by day, in your local time. Red is the model, gold is the
          market; both show the chance that the first-named team wins the series.
        </p>
      </header>

      {ctx && <EventHero ctx={ctx} timeline={timeline} timelineLoading={isChampions && champions.loading} />}

      {events.length > 1 && (
        <div className="matches-filter">
          <label className="matches-filter-label" htmlFor="event-select">EVENT</label>
          <select id="event-select" value={event} onChange={e => setEvent(e.target.value)}>
            <option value="all">All Tier 1</option>
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
              action={event !== "all" ? (
                <button type="button" className="btn btn-secondary" onClick={() => setEvent("all")}>
                  Show all Tier 1
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
                  <Stagger className="matches-board" key={`${event}-${day.key}`}>
                    {day.items.map(f => <StaggerItem key={f.match_id} className="stagger-cell"><FixtureCard f={f} /></StaggerItem>)}
                  </Stagger>
                </section>
              );
            })
          )}

          <section className="matches-day matches-finished">
            <SectionHead title="Just finished" right={<Link to="/results" className="num small">All results &rarr;</Link>} />
            {results.loading ? (
              <div className="matches-board" aria-busy="true" aria-label="Loading results">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i} className="loading-card cut-l"><div className="loading-line loading-line-wide" /><div className="loading-line loading-line-narrow" /></div>
                ))}
              </div>
            ) : results.error ? (
              <p className="muted small">Results unavailable right now ({results.error}).</p>
            ) : finished.length === 0 ? (
              <p className="muted small">No graded matches yet.</p>
            ) : (
              <Stagger className="matches-board">
                {finished.map(r => <StaggerItem key={r.match_id} className="stagger-cell"><FinishedCard r={r} /></StaggerItem>)}
              </Stagger>
            )}
          </section>
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
