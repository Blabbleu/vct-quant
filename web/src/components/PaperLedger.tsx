import { usePaperLedger } from "../lib/api";
import { pct } from "../lib/format";
import type { PaperEntry } from "../lib/types";

const signed = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(2)}`;

function Entry({ entry }: { entry: PaperEntry }) {
  const side = entry.side === "A" ? entry.team_a : entry.team_b;
  const status = entry.status === "settled" ? "Recorded result" :
    entry.status === "unverified" ? "Result unverified" : "Open / no recorded result";
  return <article className="paper-entry">
    <div className="head">
      <div className="paper-title"><b>{side}</b><span className="muted small">{entry.team_a} vs {entry.team_b}</span></div>
      <span className="chip">{status}</span>
    </div>
    <div className="muted small">Frozen {new Date(entry.entry_at).toLocaleString(undefined, { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC · <a href={`https://www.vlr.gg/${entry.match_id}`} target="_blank" rel="noopener noreferrer">Match source #{entry.match_id} ↗</a></div>
    <div className="paper-stats num small">
      <span>Model <b>{pct(entry.model)}</b></span>
      <span>Market mid <b>{pct(entry.market_mid)}</b></span>
      <span>Est. ask <b>{pct(entry.entry_price)}</b></span>
      <span>Sampled mid move <b>{entry.sampled_clv == null ? "No later quote" : `${entry.sampled_clv > 0 ? "+" : ""}${(entry.sampled_clv * 100).toFixed(1)} pts`}</b></span>
      <span>Hypothetical return <b>{entry.return_per_unit == null ? "Pending" : `${signed(entry.return_per_unit)} units`}</b></span>
    </div>
  </article>;
}

/** Read-only accounting, independent of the current fixture board's snapshot. */
export default function PaperLedgerPanel() {
  const { data, error, loading } = usePaperLedger();
  return <section className="panel pad">
    <h2>Frozen paper ledger</h2>
    <p className="muted small">One hypothetical 1-unit entry at the first liquid, pre-start, exact-ID gap of at least 10 points. No order was placed. Sampled mid move is not a close or executable CLV.</p>
    {loading ? <p role="status" className="muted">Loading paper entries…</p> :
      error || !data ? <p role="alert">Ledger unavailable: {error ?? "no data"}</p> : <>
        <div className="paper-summary num" aria-label="Paper ledger summary">
          <span>{data.n} entries</span><span>{data.settled} settled</span>
          <span>{signed(data.net_units)} hypothetical units on settled entries</span>
        </div>
        {data.rows.length ? <div className="paper-entries">{[...data.rows].reverse().map(row => <Entry key={row.match_id} entry={row} />)}</div>
          : <p className="muted">No logged pre-start gap met the frozen liquidity and identity rules.</p>}
        <p className="muted small">Ask = sampled midpoint + half-spread, not a fill; volume is not available depth. Outcomes require exact team IDs and a complete scored result. Open and unverified entries have no return. No fees, slippage or voids modeled.</p>
      </>}
  </section>;
}
