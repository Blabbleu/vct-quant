import type { HeadToHead } from "../lib/types";

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });

/** Prior Tier-1 meetings between these exact two teams (descriptive only). */
export default function HeadToHeadPanel({ h, teamA, teamB }: { h: HeadToHead; teamA: string; teamB: string }) {
  return (
    <div className="h2h">
      <p className="muted small">
        Earlier played Tier-1 series between these two exact team IDs, known before the latest forecast refresh.
        Old meetings may involve different rosters; not an adjustment to the odds.
      </p>
      {h.played === 0 ? (
        <p className="muted small">No earlier Tier-1 meeting in the recorded history.</p>
      ) : (
        <>
          <div className="h2h-tally">
            <span className="h2h-tally-side"><span className="h2h-tally-name ellipsis">{teamA}</span><span className="num h2h-tally-num">{h.wins_a}</span></span>
            <span className="h2h-tally-side"><span className="h2h-tally-name ellipsis">{teamB}</span><span className="num h2h-tally-num">{h.wins_b}</span></span>
          </div>
          <p className="muted small">
            Series wins in {h.played} meeting{h.played === 1 ? "" : "s"}
            {h.series.length < h.played ? `; newest ${h.series.length} listed` : ""}.
          </p>
          <div className="h2h-rows">
            {h.series.map(s => (
              <div className="arena-row h2h-row" key={s.match_id}>
                <span className="muted small h2h-row-date">{day(s.completed_at)}</span>
                <span className="h2h-row-winner ellipsis">{s.winner === "a" ? teamA : teamB}</span>
                <span className="num small">{s.maps_a}&ndash;{s.maps_b}</span>
                <a href={`https://www.vlr.gg/${s.match_id}`} target="_blank" rel="noreferrer" className="muted small">vlr.gg &#8599;</a>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
