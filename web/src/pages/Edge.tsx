import { Link } from "react-router-dom";
import { useSnapshot } from "../lib/api";
import { liquid, pct, when } from "../lib/format";
import { Failure, Loading, PageHead } from "../components/ui";
import TeamLogo from "../components/TeamLogo";
import TeamName, { shortName } from "../components/TeamName";

/** Paper-only view of model vs market disagreements. Never a bet slip. */
export default function Edge() {
  const { data, error, loading } = useSnapshot();
  if (loading) return <Loading />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const priced = data.fixtures.filter(f => f.market != null);
  const gaps = priced
    .map(f => {
      const gap = f.p_a - (f.market as number);
      const side = gap >= 0 ? f.team_a : f.team_b;
      const logo = gap >= 0 ? f.logo_a : f.logo_b;
      const tag = gap >= 0 ? f.tag_a : f.tag_b;
      const modelP = gap >= 0 ? f.p_a : 1 - f.p_a;
      const marketP = gap >= 0 ? (f.market as number) : 1 - (f.market as number);
      return { f, gap: Math.abs(gap), side, logo, tag, modelP, marketP, trusted: liquid(f.spread, f.volume) };
    })
    .sort((x, y) => Number(y.trusted) - Number(x.trusted) || y.gap - x.gap);
  const live = data.live;
  return (
    <>
      <PageHead eyebrow="Paper trading only" title="Edge board">
        Where the model disagrees with the betting market. A gap is not a tip: the market is often right, and on thin
        markets the price is noise. This page exists to test the model, not to place bets.
      </PageHead>

      <section className="panel">
        {gaps.length === 0 && <p className="pad muted">No priced upcoming matches.</p>}
        {gaps.map(({ f, gap, side, logo, tag, modelP, marketP, trusted }) => (
          <Link to={`/match/${f.match_id}`} className="edge-row" key={f.match_id}>
            <div className="team ellipsis"><TeamLogo src={logo} name={side} size={28} /><div className="ellipsis"><b><TeamName name={side} tag={tag} /></b><div className="muted small ellipsis">{shortName(f.team_a, f.tag_a) ?? f.team_a} vs {shortName(f.team_b, f.tag_b) ?? f.team_b} · {when(f.start)}</div></div></div>
            <div className="num right">{pct(modelP, 0)}<div className="muted small">model</div></div>
            <div className="num right">{pct(marketP, 0)}<div className="muted small">market</div></div>
            <div className="right"><span className={trusted ? "chip gap" : "chip"}>{trusted ? `+${(gap * 100).toFixed(0)} pts` : "thin"}</span></div>
          </Link>
        ))}
      </section>

      <section className="panel pad">
        <h2>How the model did against the market</h2>
        {live.market && live.market.n > 0 ? (
          <p>On {live.market.n} finished matches with a market price, the model scored <b className="num">{live.market.elo.toFixed(3)}</b> vs
            the market's <b className="num">{live.market.market.toFixed(3)}</b> (log loss, lower is better). That is far too few
            matches to call either side better yet.</p>
        ) : <p className="muted">No graded matches with a market price yet.</p>}
        <p className="muted small">Coming next: a paper-trading ledger that "bets" every trusted gap at the logged price and tracks
          profit and closing-line value over time.</p>
      </section>
    </>
  );
}
