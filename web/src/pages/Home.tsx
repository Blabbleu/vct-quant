import { Link } from "react-router-dom";
import { useSnapshot, useResults } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import SectionHead from "../components/arena/SectionHead";
import Panel from "../components/arena/Panel";
import RecordBar from "../components/arena/RecordBar";
import { LoadingBlocks, ErrorPanel, EmptyState } from "../components/arena/States";
import { COPY } from "../lib/constants";
import { recordView } from "../lib/record";
import "./Home.css";

const QUICK_LINKS = [
  { to: "/champions/2766", title: "Champions Shanghai groups", line: "Verified group results and qualifiers from the recorded bracket." },
  { to: "/rankings", title: "Power rankings", line: "The full Elo table and a head-to-head picker." },
  { to: "/edge", title: "Edge board", line: "Where the model and the market disagree most, on paper." },
  { to: "/track-record", title: "Track record", line: "Every forecast logged before the match and graded after." },
  { to: "/about", title: "How it works", line: "What the numbers mean and how to read them." },
];

export default function Home() {
  const { data, error, loading } = useSnapshot();
  const results = useResults();

  if (loading) return <LoadingBlocks label="Loading forecasts\u2026" />;
  if (error || !data) return <ErrorPanel detail={error ?? "no data"} onRetry={() => location.reload()} />;

  const next = [...data.fixtures].sort((a, b) => a.start.localeCompare(b.start)).slice(0, 5);
  const nextEvent = next[0]?.event ?? data.fixtures[0]?.event;
  const nextStage = next[0]?.series ?? data.fixtures[0]?.series;

  const record = recordView(results);

  return (
    <div className="home-page">
      <header className="page-head">
        {nextEvent && <div className="home-event num">{nextEvent}{nextStage ? ` \u00B7 ${nextStage}` : ""}</div>}
        <h1>Who wins the next VCT match?</h1>
        <p className="lede">
          Win chances for every upcoming Tier 1 match, next to what the betting market thinks, and an honest
          record of how the model has done.
        </p>
      </header>

      <div className="arena-grid home-grid">
        <div className="arena-grid-main">
          <SectionHead title="Next up" right={<Link to="/matches">All matches &rarr;</Link>} />
          {next.length === 0 ? (
            <EmptyState
              title={COPY.noMatchesScheduled}
              line={data.fixtures[0]?.event ? `Next known event: ${data.fixtures[0].event}.` : "No event is scheduled yet."}
            />
          ) : (
            <div className="home-next-list">
              {next.map(f => <FixtureCard key={f.match_id} f={f} />)}
            </div>
          )}
        </div>

        <div className="arena-grid-aside home-aside">
          <Panel cut="m" frame="line">
            <div className="pad home-record">
              <SectionHead title="Record" />
              {record.kind === "ready" ? (
                <>
                  <p className="home-record-line">{record.line}</p>
                  <RecordBar calls={record.tier.verified} hits={record.tier.favourite_won} logLoss={record.tier.log_loss} />
                </>
              ) : record.kind === "loading" ? (
                <p className="muted small" role="status">Loading the graded record&hellip;</p>
              ) : record.kind === "error" ? (
                <p className="muted small">Record unavailable right now ({record.detail}).</p>
              ) : (
                <p className="muted small">No graded Tier 1 matches yet this season.</p>
              )}
            </div>
          </Panel>

          <div className="home-links">
            {QUICK_LINKS.map(l => (
              <Link key={l.to} to={l.to} className="panel home-link cut-m">
                <span className="home-link-title">{l.title}</span>
                <span className="muted small">{l.line}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
