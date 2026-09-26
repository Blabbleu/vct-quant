import type { MatchResult } from "../lib/types";
import { pct } from "../lib/format";

const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });
const stamp = (iso: string) => new Date(iso).toLocaleString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " UTC";

/** Finished-match result, shown only when the canonical rows verify it. */
export default function ResultPanel({ r, teamA, teamB }: { r: MatchResult; teamA: string; teamB: string }) {
  const source = r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">vlr.gg ↗</a>;
  const seen = r.as_of ? <>Record last seen {stamp(r.as_of)}</> : null;
  if (r.status !== "verified") {
    return (
      <section className="panel pad">
        <h2>Result</h2>
        <p className="muted small">Marked finished, but the stored result could not be verified ({r.reason}). Not shown rather than guessed. {source}</p>
      </section>
    );
  }
  const winner = r.winner === "a" ? teamA : teamB;
  return (
    <section className="panel pad">
      <h2>Result</h2>
      <div className="kv"><span className={r.winner === "a" ? "team-win" : ""}>{teamA}</span><b className="num">{r.maps_a}</b></div>
      <div className="kv"><span className={r.winner === "b" ? "team-win" : ""}>{teamB}</span><b className="num">{r.maps_b}</b></div>
      {r.maps_complete ? (
        <div className="scroll"><table>
          <thead><tr><th>#</th><th>Map</th><th className="n">{teamA}</th><th className="n">{teamB}</th></tr></thead>
          <tbody>{r.maps.map(m => (
            <tr key={m.number}><td>{m.number}</td><td>{m.map}</td>
              <td className={`n${m.rounds_a > m.rounds_b ? " team-win" : ""}`}>{m.rounds_a}</td>
              <td className={`n${m.rounds_b > m.rounds_a ? " team-win" : ""}`}>{m.rounds_b}</td></tr>
          ))}</tbody>
        </table></div>
      ) : <p className="muted small">Map scores not stored for this match yet; the series score above is from the result listing.</p>}
      {r.pre_start_winner_p != null && (
        <p className="muted small">Last pre-start model forecast gave {winner} {pct(r.pre_start_winner_p)}. One match says little about calibration; see Track record.</p>
      )}
      <p className="muted small">{r.completed_on ? <>Completed {day(r.completed_on)} (date only). </> : null}{seen}{seen && source ? " · " : null}{source}</p>
    </section>
  );
}
