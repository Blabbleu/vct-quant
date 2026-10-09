import { Link } from "react-router-dom";
import Panel from "../arena/Panel";
import "./EventHero.css";
import { Chip } from "../arena/Chip";
import { formatCountdown, stageShort, type EventContext, type TimelineStage } from "../../lib/matchesData";
import { useNow } from "../../lib/useNow";
import { m, useInitial, EASE_OUT, D_BASE } from "../../lib/motion";
import type { Fixture } from "../../lib/types";
import { stageSpan } from "../../lib/format";

const tagOf = (f: Fixture, side: "a" | "b") => ((side === "a" ? f.tag_a ?? f.team_a : f.tag_b ?? f.team_b)).toUpperCase();

/**
 * Event context strip at the top of Matches: event + phase, a live-ticking countdown to the
 * next kick-off, the slate size, and (when the Champions feed is in) the stage tracker.
 */
export default function EventHero({ ctx, timeline, timelineLoading }: {
  ctx: EventContext; timeline: TimelineStage[]; timelineLoading: boolean;
}) {
  const now = useNow(1000);
  const init = useInitial("hidden");
  const f = ctx.next;
  const ms = new Date(f.start).getTime() - now;
  const live = ms <= 0;
  const stageText = ctx.stages.length === 1 ? ctx.stages[0] : ctx.stages.length > 1 ? `${ctx.stages.length} stages` : "";
  return (
    <Panel cut="l" frame="line" brackets className="event-hero">
      <div className="event-hero-in">
        <div className="event-hero-main">
          <div className="event-hero-eyebrow num">{ctx.event}{ctx.phase ? ` \u00B7 ${ctx.phase}` : ""}</div>
          <div className="event-hero-stage">{stageText || "Upcoming"}</div>
          <div className="event-hero-facts num">
            <span><b>{ctx.matches}</b> {ctx.matches === 1 ? "match" : "matches"}</span>
            <span><b>{ctx.days}</b> {ctx.days === 1 ? "day" : "days"}</span>
            {ctx.bestOf.length > 0 && <span>{ctx.bestOf.map(b => `Bo${b}`).join(" / ")}</span>}
            <span>Tier 1</span>
          </div>
        </div>

        <div className="event-hero-clock">
          <div className="event-hero-clock-label">{live ? "Started" : "Next kick-off in"}</div>
          <div className={`event-hero-count num${live ? " event-hero-count-live" : ""}`} aria-live="off">
            {live ? <><span className="live-dot" aria-hidden="true" />LIVE</> : formatCountdown(ms)}
          </div>
          <Link to={`/match/${f.match_id}`} className="event-hero-next num">
            {tagOf(f, "a")} <span className="vs">vs</span> {tagOf(f, "b")} &middot; {stageShort(f.series)}
          </Link>
        </div>

        <div className="event-hero-track" aria-label="Event stages">
          {timeline.length > 0 ? (
            <ol className="event-stages">
              {timeline.map((t, i) => (
                <m.li
                  key={t.stage}
                  className={`event-stage${t.current ? " event-stage-current" : ""}${t.past ? " event-stage-past" : ""}`}
                  initial={init} animate="show"
                  variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0 } }}
                  transition={{ duration: D_BASE, ease: EASE_OUT, delay: 0.1 + i * 0.04 }}
                  title={`${t.stage}: ${t.matches} ${t.matches === 1 ? "match" : "matches"}${t.bestOf ? `, Bo${t.bestOf}` : ""}`}
                >
                  <span className="event-stage-name">{t.short}</span>
                  <span className="event-stage-date num">{stageSpan(t.start, t.end)}</span>
                </m.li>
              ))}
            </ol>
          ) : timelineLoading ? (
            <div className="event-stages event-stages-skel" aria-hidden="true">
              {Array.from({ length: 5 }, (_, i) => <span key={i} className="event-stage event-stage-skel" />)}
            </div>
          ) : (
            <Chip variant="ghost">STAGE SCHEDULE NOT PUBLISHED</Chip>
          )}
        </div>
      </div>
    </Panel>
  );
}
