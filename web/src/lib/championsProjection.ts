import type { ChampionsProjection, ChampionsProjectionCandidate, ChampionsProjectionSlot } from "./types";

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
  return [...projection.teams].sort((a, b) => b.p_title - a.p_title).map(team => ({
    ...team,
    p_upper_final: team.p_reach["Upper Final"] ?? team.p_reach.UF ?? 0,
    p_grand_final: team.p_reach["Grand Final"] ?? team.p_reach.GF ?? 0,
  }));
}
