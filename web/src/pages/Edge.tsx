import { Link } from "react-router-dom";
import { useSnapshot, usePaperLedger } from "../lib/api";
import { liquid, pct, when } from "../lib/format";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import GapChip from "../components/arena/GapChip";
import { Chip } from "../components/arena/Chip";
import SectionHead from "../components/arena/SectionHead";
import StatCell from "../components/arena/StatCell";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import { COPY } from "../lib/constants";
import type { PaperEntry } from "../lib/types";
import "./Edge.css";

const signed = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(2)}`;

/** One row of the dense paper ledger table: entry odds, result, units. */
function LedgerRow({ entry }: { entry: PaperEntry }) {
  const side = entry.side === "A" ? entry.team_a : entry.team_b;
  const other = entry.side === "A" ? entry.team_b : entry.team_a;
  const statusLabel = entry.status === "settled" ? "SETTLED" : entry.status === "unverified" ? "UNVERIFIED" : "OPEN";
  return (
    <tr>
      <td>
        <Link to={`/match/${entry.match_id}`} className="edge-ledger-match">
          <b>{side}</b>
          <span className="muted small ellipsis">vs {other}</span>
        </Link>
      </td>
      <td className="num n">{pct(entry.model, 0)}</td>
      <td className="num n">{pct(entry.entry_price, 0)}</td>
      <td className="n"><Chip variant={entry.status === "settled" ? "default" : "ghost"}>{statusLabel}</Chip></td>
      <td className={`num n edge-ledger-units${entry.return_per_unit != null ? (entry.return_per_unit > 0 ? " edge-ledger-pos" : entry.return_per_unit < 0 ? " edge-ledger-neg" : "") : ""}`}>
        {entry.return_per_unit == null ? "\u2013" : signed(entry.return_per_unit)}
      </td>
    </tr>
  );
}

/** Paper-only view of model vs market disagreements. Never a bet slip. */
export default function Edge() {
  const { data, error, loading } = useSnapshot();
  const { data: ledger, error: ledgerError, loading: ledgerLoading } = usePaperLedger();

  if (loading) return <div className="edge-page"><LoadingBlocks label="Loading edge board\u2026" /></div>;
  if (error || !data) return <div className="edge-page"><ErrorPanel detail={error ?? "no data"} onRetry={() => location.reload()} /></div>;

  const priced = data.fixtures.filter(f => f.market != null);
  const gaps = priced
    .map(f => {
      const gap = f.p_a - (f.market as number);
      const side = gap >= 0 ? f.team_a : f.team_b;
      const logo = gap >= 0 ? f.logo_a : f.logo_b;
      const tag = gap >= 0 ? f.tag_a : f.tag_b;
      const modelP = gap >= 0 ? f.p_a : 1 - f.p_a;
      const trusted = liquid(f.spread, f.volume);
      return { f, gap: Math.abs(gap), side, logo, tag, modelP, trusted };
    })
    // Biggest disagreements first among trusted markets; thin markets pushed last.
    .sort((x, y) => Number(y.trusted) - Number(x.trusted) || y.gap - x.gap);

  const unpriced = data.fixtures.filter(f => f.market == null);
  const live = data.live;

  return (
    <div className="edge-page">
      <header className="edge-head">
        <h1 className="edge-title">Edge board</h1>
        <p className="edge-lede">Where the model disagrees with the betting market. A gap is not a tip: the market is often right, and on thin markets the price is noise. This page exists to test the model, not to place bets.</p>
        <p className="edge-disclaimer slant"><span>{COPY.edgeDisclaimer}</span></p>
      </header>

      <div className="edge-grid">
        <div className="edge-main">
          <SectionHead title="Biggest disagreements" right={<span className="muted small">{gaps.length} priced</span>} />
          {gaps.length === 0 && <p className="muted">No priced upcoming matches.</p>}
          <div className="edge-list">
            {gaps.map(({ f, side, logo, tag, modelP }) => (
              <Link to={`/match/${f.match_id}`} className="edge-item cut-m" key={f.match_id}>
                <LogoSlot src={logo} name={side} tag={tag} size={34} />
                <div className="edge-item-mid">
                  <TeamLabel name={side} tag={tag} mode="auto" />
                  <div className="muted small ellipsis">
                    {f.tag_a ?? f.team_a} vs {f.tag_b ?? f.team_b} &middot; {when(f.start)}
                  </div>
                </div>
                <div className="edge-item-nums">
                  <div className="edge-item-num">
                    <span className="num edge-item-model">{pct(modelP, 0)}</span>
                    <span className="edge-item-k">model</span>
                  </div>
                  <GapChip model={f.p_a} market={f.market} spread={f.spread}
                    favouredLabel={`${f.p_a >= 0.5 ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)} FAVOURED`} />
                </div>
              </Link>
            ))}
          </div>

          {unpriced.length > 0 && (
            <>
              <SectionHead title="No market price yet" right={<span className="muted small">{unpriced.length}</span>} />
              <div className="edge-list">
                {unpriced.map(f => (
                  <Link to={`/match/${f.match_id}`} className="edge-item cut-m" key={f.match_id}>
                    <LogoSlot src={f.p_a >= 0.5 ? f.logo_a : f.logo_b} name={f.p_a >= 0.5 ? f.team_a : f.team_b}
                      tag={f.p_a >= 0.5 ? f.tag_a : f.tag_b} size={34} />
                    <div className="edge-item-mid">
                      <TeamLabel name={f.p_a >= 0.5 ? f.team_a : f.team_b} tag={f.p_a >= 0.5 ? f.tag_a : f.tag_b} mode="auto" />
                      <div className="muted small ellipsis">{f.tag_a ?? f.team_a} vs {f.tag_b ?? f.team_b} &middot; {when(f.start)}</div>
                    </div>
                    <div className="edge-item-nums">
                      <GapChip model={f.p_a} market={null}
                        favouredLabel={`${f.p_a >= 0.5 ? (f.tag_a ?? f.team_a) : (f.tag_b ?? f.team_b)} FAVOURED`} />
                    </div>
                  </Link>
                ))}
              </div>
            </>
          )}

          <SectionHead title="How the model did against the market" />
          <div className="edge-scorecard">
            {live.market && live.market.n > 0 ? (
              <>
                <StatCell label="Model" value={live.market.elo.toFixed(3)} tone="model" />
                <StatCell label="Market" value={live.market.market.toFixed(3)} tone="market" />
                <StatCell label="Matches" value={live.market.n} />
              </>
            ) : <p className="muted">No graded matches with a market price yet.</p>}
          </div>
          {live.market && live.market.n > 0 && (
            <p className="muted small">Log loss on {live.market.n} finished matches with a market price, lower is better. That is far too few matches to call either side better yet.</p>
          )}
        </div>

        <aside className="edge-aside">
          <SectionHead title="Paper ledger" />
          <p className="edge-ledger-note">
            One hypothetical 1-unit entry at the first liquid, pre-start, exact-ID gap of at least 10 points. No order was placed.
          </p>
          {ledgerLoading ? <LoadingBlocks rows={2} /> :
            ledgerError || !ledger ? <ErrorPanel detail={ledgerError ?? "no data"} /> : (
              <>
                <div className="edge-ledger-summary">
                  <StatCell label="Entries" value={ledger.n} />
                  <StatCell label="Settled" value={ledger.settled} />
                  <StatCell label="Net units" value={signed(ledger.net_units)}
                    tone={ledger.net_units > 0 ? "model" : ledger.net_units < 0 ? "market" : undefined} />
                </div>
                <div className="edge-ledger-scroll">
                  <table className="edge-ledger-table">
                    <thead>
                      <tr><th>Match</th><th className="n">Model</th><th className="n">Entry</th><th className="n">Status</th><th className="n">Units</th></tr>
                    </thead>
                    <tbody>
                      {ledger.rows.length
                        ? [...ledger.rows].reverse().map(row => <LedgerRow key={row.match_id} entry={row} />)
                        : <tr><td colSpan={5} className="muted">No logged pre-start gap met the frozen liquidity and identity rules.</td></tr>}
                    </tbody>
                  </table>
                </div>
                <p className="edge-ledger-note">
                  Ask = sampled midpoint + half-spread, not a fill. Open and unverified entries have no return. No fees, slippage or voids modeled.
                </p>
              </>
            )}
        </aside>
      </div>
    </div>
  );
}
