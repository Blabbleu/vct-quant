import type { ResultsList } from "./types";

export type TierRecord = ResultsList["by_tier"][string];

export type RecordView =
  | { kind: "loading" }
  | { kind: "error"; detail: string }
  | { kind: "empty" }
  | { kind: "ready"; tier: TierRecord; line: string };

/**
 * Home "Record" box state from the /api/results fetch. /api/results replays the
 * model in Python and takes several seconds, while /api/snapshot answers at once,
 * so Home renders with `data === null` first. That in-flight state must read as
 * "loading", never as "no graded matches" (the original bug). A tier with zero
 * verified rows is also "empty", not a 0-of-0 bar.
 */
export function recordView(
  results: { data: ResultsList | null; error: string | null; loading: boolean },
  tierKey = "1",
): RecordView {
  if (results.loading) return { kind: "loading" };
  if (results.error) return { kind: "error", detail: results.error };
  const tier = results.data?.by_tier?.[tierKey];
  if (!tier || !(tier.verified > 0)) return { kind: "empty" };
  return {
    kind: "ready",
    tier,
    line: `Model picked the winner in ${tier.favourite_won} of ${tier.verified} graded Tier ${tierKey} matches.`,
  };
}
