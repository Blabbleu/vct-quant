import { Link } from "react-router-dom";
import { useSnapshot } from "../lib/api";
import { int, num, pct } from "../lib/format";
import FixtureCard from "../components/FixtureCard";
import { Failure, Loading, PageHead, Tile } from "../components/ui";

export default function Home() {
  const { data, error, loading } = useSnapshot();
  if (loading) return <Loading />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const next = [...data.fixtures].sort((a, b) => a.start.localeCompare(b.start)).slice(0, 3);
  const live = data.live;
  return (
    <>
      <PageHead eyebrow={`Valorant Champions Tour · ${data.season}`} title="Who wins the next VCT match?">
        Win chances for every upcoming Tier-1 match, next to what the betting market thinks, and an honest record
        of how the model has done.
      </PageHead>

      <div className="tiles">
        <Tile hero value={live.graded ? num(live.log_loss, 3) : "–"} label={`Live score · ${live.graded} matches graded (lower is better)`} />
        <Tile value={pct(data.backtest.accuracy)} label={`Picks the winner · ${int(data.backtest.n)} past matches`} />
        <Tile value={data.fixtures.length} label="Upcoming matches forecast" />
        <Tile value={int(data.coverage.matches)} label="Matches in the database" />
      </div>

      <section>
        <div className="head"><h2>Next up</h2><Link to="/matches">All matches →</Link></div>
        <div className="cards">{next.map(f => <FixtureCard key={f.match_id} f={f} />)}</div>
      </section>

      <section className="grid-2">
        <Link to="/rankings" className="panel pad link-panel">
          <h2>Power rankings</h2>
          <p className="muted">{data.rankings.slice(0, 3).map(r => r.team).join(", ")} lead the {data.season} Elo table.</p>
        </Link>
        <Link to="/edge" className="panel pad link-panel">
          <h2>Edge board</h2>
          <p className="muted">Where the model and the market disagree most, and how betting those gaps would have done on paper.</p>
        </Link>
        <Link to="/track-record" className="panel pad link-panel">
          <h2>Track record</h2>
          <p className="muted">Every forecast logged before the match and graded after. Nothing deleted.</p>
        </Link>
        <Link to="/about" className="panel pad link-panel">
          <h2>How it works</h2>
          <p className="muted">What the numbers mean and how to read them, in two minutes.</p>
        </Link>
      </section>
    </>
  );
}
