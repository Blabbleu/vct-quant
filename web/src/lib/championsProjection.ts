import type { ChampionsPlayoffs, ChampionsProjection, ChampionsProjectionCandidate, ChampionsProjectionSlot } from "./types";

export function routingChip(playoffs: Pick<ChampionsPlayoffs, "routing" | "projection">): string {
  const projection = playoffs.projection;
  if (playoffs.routing !== "projected" || !projection || "withheld" in projection || !("slots" in projection)) {
    return "ROUTING UNCONFIRMED";
  }
  return "PROJECTED ROUTING";
}

export function mergeCandidates(slot: ChampionsProjectionSlot | null | undefined): ChampionsProjectionCandidate[] {
  if (!slot || !Array.isArray(slot.candidates)) return [];
  const pairs = new Map<string, { ids: [number, number]; weight: number; aWeight: number }>();
  for (const c of slot.candidates) {
    if (!c || !Array.isArray(c.team_ids) || c.team_ids.length !== 2 || !(c.p_pairing > 0) || !Number.isFinite(c.p_pairing)) continue;
    const [a, b] = c.team_ids;
    const ids: [number, number] = a <= b ? [a, b] : [b, a];
    const key = `${ids[0]}:${ids[1]}`;
    const orientedPa = a === ids[0] ? c.p_a : 1 - c.p_a;
    const item = pairs.get(key) ?? { ids, weight: 0, aWeight: 0 };
    item.weight += c.p_pairing;
    item.aWeight += c.p_pairing * orientedPa;
    pairs.set(key, item);
  }
  return [...pairs.values()].map(x => ({ team_ids: x.ids, p_pairing: x.weight, p_a: x.aWeight / x.weight }))
    .sort((a, b) => b.p_pairing - a.p_pairing);
}

export function mostLikely(slot: ChampionsProjectionSlot | null | undefined): ChampionsProjectionCandidate | null {
  return mergeCandidates(slot)[0] ?? null;
}

export function titleTable(projection: ChampionsProjection | { withheld: string } | null | undefined) {
  if (!projection || "withheld" in projection) return [];
  const reach = (team: ChampionsProjection["teams"][number], key: string, alias: string) => {
    const value = team.p_reach?.[key] ?? team.p_reach?.[alias];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  };
  return projection.teams.filter(team => Number.isFinite(team.p_title) && team.p_title >= 0 && team.p_title <= 1)
    .map(team => ({
    ...team,
    p_upper_final: reach(team, "Upper Final", "UF"),
    p_grand_final: reach(team, "Grand Final", "GF"),
  })).sort((a, b) => b.p_title - a.p_title || b.p_grand_final - a.p_grand_final || a.team_id - b.team_id);
}
