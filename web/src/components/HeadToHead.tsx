import type { HeadToHead } from "../lib/types";

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });

/** Prior Tier-1 meetings between these exact two teams (descriptive only). */
export default function HeadToHeadPanel({ h, teamA, teamB }: { h: HeadToHead; teamA: string; teamB: string }) {
  return (
    <section className="panel pad">
      <h2>Head to head</h2>
      <p className="muted small">Earlier played Tier-1 series between these two exact team IDs, known before the latest forecast refresh. Old meetings may involve different rosters; not an adjustment to the odds.</p>
      {h.played === 0 ? <p className="muted small">No earlier Tier-1 meeting in the recorded history.</p> : (
        <>
          <div className="kv"><span>{teamA}</span><b className="num">{h.wins_a}</b></div>
          <div className="kv"><span>{teamB}</span><b className="num">{h.wins_b}</b></div>
          <p className="muted small">Series wins in {h.played} meeting{h.played === 1 ? "" : "s"}{h.series.length < h.played ? `; newest ${h.series.length} listed` : ""}.</p>
          <div className="scroll"><table>
            <thead><tr><th>Date (UTC)</th><th>Winner</th><th className="n">Maps</th><th>Source</th></tr></thead>
            <tbody>{h.series.map(s => (
              <tr key={s.match_id}>
                <td>{day(s.completed_at)}</td>
                <td className="team-win">{s.winner === "a" ? teamA : teamB}</td>
                <td className="n">{s.maps_a}–{s.maps_b}</td>
                <td><a href={`https://www.vlr.gg/${s.match_id}`} target="_blank" rel="noreferrer">vlr.gg ↗</a></td>
              </tr>
            ))}</tbody>
          </table></div>
        </>
      )}
    </section>
  );
}
