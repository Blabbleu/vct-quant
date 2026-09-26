import LogoSlot from "./LogoSlot";
import TeamLabel from "./TeamLabel";
import { Chip } from "./Chip";
import "./ScoreBug.css";

/**
 * Finished-match scoreboard: both teams' logos and names either side of the
 * final series score in Num XL mono. The winner's number takes --result and
 * a slanted WIN tag; the loser's name drops to --text-3 and its logo fades.
 */
export default function ScoreBug({
  teamA, tagA, logoA, teamB, tagB, logoB, mapsA, mapsB, winner,
}: {
  teamA: string; tagA?: string | null; logoA?: string | null;
  teamB: string; tagB?: string | null; logoB?: string | null;
  mapsA: number; mapsB: number; winner: "a" | "b";
}) {
  return (
    <div className="scorebug">
      <div className={`scorebug-side${winner === "b" ? " scorebug-side-loser" : ""}`}>
        <LogoSlot src={logoA} name={teamA} tag={tagA} size={56} faded={winner === "b"} />
        <div className="scorebug-info">
          <TeamLabel name={teamA} tag={tagA} mode="auto" />
          {winner === "a" && <Chip variant="result">WIN</Chip>}
        </div>
      </div>
      <div className="scorebug-score">
        <span className={`scorebug-num num${winner === "a" ? " scorebug-num-win" : ""}`}>{mapsA}</span>
        <span className="scorebug-sep num">&ndash;</span>
        <span className={`scorebug-num num${winner === "b" ? " scorebug-num-win" : ""}`}>{mapsB}</span>
      </div>
      <div className={`scorebug-side scorebug-side-right${winner === "a" ? " scorebug-side-loser" : ""}`}>
        <div className="scorebug-info scorebug-info-right">
          {winner === "b" && <Chip variant="result">WIN</Chip>}
          <TeamLabel name={teamB} tag={tagB} mode="auto" />
        </div>
        <LogoSlot src={logoB} name={teamB} tag={tagB} size={56} faded={winner === "a"} />
      </div>
    </div>
  );
}
