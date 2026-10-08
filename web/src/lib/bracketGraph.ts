/**
 * Champions 2026 playoff bracket as a graph, built from the /api/champions payload.
 *
 * Pure and dependency-free (type-only imports) so node's test runner can load it
 * directly (test/bracketGraph.test.js).
 *
 * WHAT IS VERIFIED vs ASSUMED
 *   - The four Upper Quarterfinal pairings, their kick-offs and Bo come from the API
 *     (`playoffs.opening`) and are officially verified.
 *   - Scheduled sides and results are shown when supplied by the API; missing data stays TBD.
 *   - The EDGES below (who feeds whom) follow VLR's bracket layout. They are NOT officially
 *     confirmed (the API says `routing: "unresolved"`), so every edge is `confirmed: false`.
 *     The candidate renderer must style and label them as projections; do not surface any
 *     edge as an official route until each one is directly source-verified.
 */
import type { ChampionsPlayoffMatch, ChampionsPlayoffs, ChampionsPlayoffSide, ChampionsPlayoffSlot } from "./types";

export type BracketSection = "upper" | "lower" | "final";
export type RoundKey = "UQF" | "USF" | "UF" | "LR1" | "LR2" | "LR3" | "LF" | "GF";
export interface Feed { from: number; take: "winner" | "loser" }

interface Topology { code: string; round: RoundKey; section: BracketSection; feeds: Feed[] }

const W = (from: number): Feed => ({ from, take: "winner" });
const L = (from: number): Feed => ({ from, take: "loser" });

/** The single place the edge graph is encoded (vlr.gg match ids, VLR layout order). */
export const BRACKET_TOPOLOGY: Readonly<Record<number, Topology>> = {
  754730: { code: "UQF1", round: "UQF", section: "upper", feeds: [] },
  754731: { code: "UQF2", round: "UQF", section: "upper", feeds: [] },
  754732: { code: "UQF3", round: "UQF", section: "upper", feeds: [] },
  754733: { code: "UQF4", round: "UQF", section: "upper", feeds: [] },
  754734: { code: "USF1", round: "USF", section: "upper", feeds: [W(754730), W(754731)] },
  754735: { code: "USF2", round: "USF", section: "upper", feeds: [W(754732), W(754733)] },
  754736: { code: "UF", round: "UF", section: "upper", feeds: [W(754734), W(754735)] },
  754738: { code: "LR1-1", round: "LR1", section: "lower", feeds: [L(754730), L(754731)] },
  754739: { code: "LR1-2", round: "LR1", section: "lower", feeds: [L(754732), L(754733)] },
  754740: { code: "LR2-1", round: "LR2", section: "lower", feeds: [W(754738), L(754734)] },
  754741: { code: "LR2-2", round: "LR2", section: "lower", feeds: [W(754739), L(754735)] },
  754742: { code: "LR3", round: "LR3", section: "lower", feeds: [W(754740), W(754741)] },
  754743: { code: "LF", round: "LF", section: "lower", feeds: [W(754742), L(754736)] },
  754737: { code: "GF", round: "GF", section: "final", feeds: [W(754736), W(754743)] },
};

export interface BracketNode {
  id: number;
  code: string;
  round: RoundKey;
  section: BracketSection;
  stage: string;
  start: string | null;
  bestOf: number | null;
  url: string | null;
  /** Two named sides are available from the payload. */
  verified: boolean;
  sides: [ChampionsPlayoffSide, ChampionsPlayoffSide] | null;
  result: { winner_team_id: number; scores: [number, number] } | null;
  match: ChampionsPlayoffMatch | null;
  feeds: Feed[];
}

export interface BracketEdge {
  id: string;
  from: number;
  to: number;
  take: "winner" | "loser";
  /** False for every edge until routing is officially published. */
  confirmed: boolean;
}

export interface FlowSide {
  nodeId: number;
  edgeId: string;
  teamId: number;
  name: string;
  tag: string | null;
  logo: string | null;
  /** Model probability of this team winning the match (= advancing along the winner edge). */
  pWin: number;
  favourite: boolean;
}

export interface BracketGraph {
  nodes: BracketNode[];
  edges: BracketEdge[];
  byId: Map<number, BracketNode>;
  /** Payload slots we could not place in the topology (schedule changed upstream). */
  unmapped: number[];
  flows: FlowSide[];
}

/** Edges the chart draws as connectors: winner advancement only (within-bracket progression + into the Grand Final). */
export function progressionEdges(edges: readonly BracketEdge[]): BracketEdge[] {
  return edges.filter(e => e.take === "winner");
}

/** Loser drop-in edges. Never drawn as lines; shown as slot labels ("Loser UQF1") plus a hover highlight. */
export function dropInEdges(edges: readonly BracketEdge[]): BracketEdge[] {
  return edges.filter(e => e.take === "loser");
}

/** Edges along which the loser of `nodeId` drops into the lower bracket. */
export function dropTargets(graph: Pick<BracketGraph, "edges">, nodeId: number): BracketEdge[] {
  return dropInEdges(graph.edges).filter(e => e.from === nodeId);
}

/** Human label for an unresolved slot feeding a node, e.g. "Winner UQF1". */
export function feedLabel(feed: Feed): string {
  const t = BRACKET_TOPOLOGY[feed.from];
  return `${feed.take === "winner" ? "Winner" : "Loser"} ${t ? t.code : feed.from}`;
}

export function buildBracketGraph(playoffs: Pick<ChampionsPlayoffs, "opening" | "schedule" | "unverified_match_ids">): BracketGraph {
  const nodes: BracketNode[] = [];
  const byId = new Map<number, BracketNode>();
  const unmapped: number[] = [];

  const unverified = new Set(playoffs.unverified_match_ids ?? []);
  const add = (slot: ChampionsPlayoffSlot | ChampionsPlayoffMatch, match: ChampionsPlayoffMatch | null) => {
    const topo = BRACKET_TOPOLOGY[slot.match_id];
    if (!topo) { unmapped.push(slot.match_id); return; }
    if (byId.has(slot.match_id)) return;
    const node: BracketNode = {
      id: slot.match_id, code: topo.code, round: topo.round, section: topo.section,
      stage: slot.stage, start: slot.start, bestOf: slot.best_of,
      url: match?.url ?? null, verified: slot.sides?.length === 2,
      sides: slot.sides?.length === 2 ? slot.sides : null,
      result: unverified.has(slot.match_id) ? null : validResult(slot.result, slot.sides),
      match, feeds: topo.feeds,
    };
    byId.set(node.id, node);
    nodes.push(node);
  };
  for (const m of playoffs.opening) add(m, m);
  for (const s of playoffs.schedule) add(s, null);

  const edges: BracketEdge[] = [];
  for (const node of nodes) {
    for (const f of node.feeds) {
      if (!byId.has(f.from)) continue;
      edges.push({ id: `${f.from}-${f.take}-${node.id}`, from: f.from, to: node.id, take: f.take, confirmed: false });
    }
  }

  // Team flow: each side of a verified match travels along the winner edge out of that match,
  // weighted by the model's win probability. No flow for a side without a forecast.
  const flows: FlowSide[] = [];
  for (const node of nodes) {
    if (!node.sides || node.result) continue;
    const out = edges.find(e => e.from === node.id && e.take === "winner");
    if (!out) continue;
    const [a, b] = node.sides;
    const pa = valid(a.p_win), pb = valid(b.p_win);
    for (const [s, p, other] of [[a, pa, pb], [b, pb, pa]] as const) {
      if (p == null) continue;
      // Strict: an exact tie has no favourite.
      flows.push(flowSide(node.id, out.id, s, p, other == null ? p >= 0.5 : p > other));
    }
  }

  return { nodes, edges, byId, unmapped, flows };
}

function validResult(result: ChampionsPlayoffSlot["result"], sides: ChampionsPlayoffSlot["sides"]) {
  if (!result || !sides || result.scores.length !== 2 || !sides.some(s => s.team_id === result.winner_team_id)) return null;
  if (!result.scores.every(score => Number.isInteger(score) && score >= 0) || result.scores[0] === result.scores[1]) return null;
  const winnerIndex = sides.findIndex(s => s.team_id === result.winner_team_id);
  return result.scores[winnerIndex] > result.scores[1 - winnerIndex] ? result : null;
}

function valid(p: number | null): number | null {
  return p != null && Number.isFinite(p) && p >= 0 && p <= 1 ? p : null;
}

function flowSide(nodeId: number, edgeId: string, s: ChampionsPlayoffSide, pWin: number, favourite: boolean): FlowSide {
  return { nodeId, edgeId, teamId: s.team_id, name: s.name, tag: s.tag, logo: s.logo, pWin, favourite };
}
