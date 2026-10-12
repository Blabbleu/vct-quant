import { Link } from "react-router-dom";
import { useSnapshot, useResults } from "../lib/api";
import FixtureCard from "../components/FixtureCard";
import SectionHead from "../components/arena/SectionHead";
import { ModelRecord, PowerRanks, RecentResults } from "../components/matches/RailPanels";
import { LoadingBlocks, ErrorPanel, EmptyState } from "../components/arena/States";
import { COPY } from "../lib/constants";
import { homeEmptyLine, homeHeadlineCopy } from "../lib/homeCopy";
import { PageFade, Words, Stagger, StaggerItem, Reveal } from "../lib/motion";
import "./Home.css";

const QUICK_LINKS = [
  { to: "/champions/2766", title: "Champions Shanghai", line: "Playoff bracket, title odds and verified results." },
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

  const next = [...data.fixtures].sort((a, b) => a.start.localeCompare(b.start)).slice(0, 6);
  const nextEvent = next[0]?.event ?? data.fixtures[0]?.event;
  const nextStage = next[0]?.series ?? data.fixtures[0]?.series;
  const headlineCopy = homeHeadlineCopy(data.fixtures.length > 0);


  return (
    <PageFade className="home-page">
      <header className="page-head">
        {nextEvent && <div className="home-event num">{nextEvent}{nextStage ? ` \u00B7 ${nextStage}` : ""}</div>}
        <Words text={headlineCopy.headline} />
        <span className="home-sweep" aria-hidden="true" />
        <p className="lede">
          {headlineCopy.lede}
        </p>
      </header>

      <div className="page-split">
        <div className="page-split-main">
          <SectionHead title="Next up" right={<Link to="/matches">All matches &rarr;</Link>} />
          {next.length === 0 ? (
            <EmptyState
              title={COPY.noMatchesScheduled}
              line={homeEmptyLine(data.fixtures.length)}
            />
          ) : (
            <Stagger className="fill-board">
              {next.map(f => <StaggerItem key={f.match_id} className="stagger-cell"><FixtureCard f={f} /></StaggerItem>)}
            </Stagger>
          )}

          <Reveal className="home-quick-wrap">
            <SectionHead title="Explore" />
            <Stagger className="home-links">
              {QUICK_LINKS.map(l => (
                <StaggerItem key={l.to} lift>
                  <Link to={l.to} className="panel home-link cut-m">
                    <span className="home-link-title">{l.title}</span>
                    <span className="muted small">{l.line}</span>
                  </Link>
                </StaggerItem>
              ))}
            </Stagger>
          </Reveal>
        </div>

        <aside className="page-split-rail" aria-label="Context">
          <ModelRecord results={results} index={0} />
          <RecentResults results={results} index={1} />
          <PowerRanks rankings={data.rankings} index={2} />
        </aside>
      </div>
    </PageFade>
  );
}
