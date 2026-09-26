import type { MatchResult } from "../lib/types";
import { pct } from "../lib/format";
import ScoreBug from "./arena/ScoreBug";
import MapStrip from "./arena/MapStrip";
import SectionHead from "./arena/SectionHead";

const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" });
const stamp = (iso: string) => new Date(iso).toLocaleString(undefined,
  { timeZone: "UTC", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " UTC";

/**
 * Finished-match result: score bug (final score, WIN tag, faded loser) plus
 * the map-by-map strip. When the stored result cannot be verified, this
 * shows the spec's honest miss instead of guessing at a score.
 */
export default function ResultPanel({
  r, teamA, teamB, tagA, tagB, logoA, logoB,
}: {
  r: MatchResult; teamA: string; teamB: string;
  tagA?: string | null; tagB?: string | null; logoA?: string | null; logoB?: string | null;
}) {
  const source = r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">vlr.gg &#8599;</a>;
  const seen = r.as_of ? <>Record last seen {stamp(r.as_of)}</> : null;

  if (r.status !== "verified") {
    return (
      <div className="match-result">
        <SectionHead title="Result" />
        <p className="muted small">
          Marked finished, but the stored result could not be verified ({r.reason}). Not shown rather than guessed. {source}
        </p>
      </div>
    );
  }

  const winner = r.winner === "a" ? "a" : "b";
  const mapsPlayed = (r.maps_a ?? 0) + (r.maps_b ?? 0);

  return (
    <div className="match-result">
      <ScoreBug
        teamA={teamA} tagA={tagA} logoA={logoA}
        teamB={teamB} tagB={tagB} logoB={logoB}
        mapsA={r.maps_a ?? 0} mapsB={r.maps_b ?? 0} winner={winner}
      />
      <MapStrip maps={r.maps} mapsPlayed={mapsPlayed} teamA={teamA} teamB={teamB} />
      {!r.maps_complete && r.maps.length === 0 && (
        <p className="muted small">Map scores not stored for this match yet; the series score above is from the result listing.</p>
      )}
      {r.pre_start_winner_p != null && (
        <p className="muted small">
          Last pre-start model forecast gave {r.winner === "a" ? teamA : teamB} {pct(r.pre_start_winner_p)}.
          One match says little about calibration; see Track record.
        </p>
      )}
      <p className="muted small">
        {r.completed_on ? <>Completed {day(r.completed_on)} (date only). </> : null}
        {seen}{seen && source ? " \u00B7 " : null}{source}
      </p>
    </div>
  );
}
