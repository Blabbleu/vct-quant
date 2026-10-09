import type { ChampionsPlayoffMatch } from "./types";

export function openingSectionCopy(
  opening: ChampionsPlayoffMatch[],
  unverifiedIds: number[],
): { chip: string; played: number; total: number } {
  const unverified = new Set(unverifiedIds);
  const played = opening.filter(match =>
    match.result != null &&
    !unverified.has(match.match_id) &&
    match.sides.some(side => side.team_id === match.result!.winner_team_id),
  ).length;
  const total = opening.length;
  const chip = played === 0
    ? "DRAWN · ROUTING TBD"
    : played === total
      ? "COMPLETE"
      : `${played}/${total} PLAYED`;
  return { chip, played, total };
}
