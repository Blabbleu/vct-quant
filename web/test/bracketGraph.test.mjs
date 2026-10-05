import test from "node:test";
import assert from "node:assert/strict";
import { buildBracketGraph, progressionEdges, dropInEdges, dropTargets } from "../src/lib/bracketGraph.ts";

const names = ["100 Thieves", "G2", "Vitality", "Nongshim", "NRG", "T1", "PRX", "LOUD"];
const opening = Array.from({ length: 4 }, (_, i) => ({
  match_id: 754730 + i,
  stage: "Upper Quarterfinals",
  start: null,
  best_of: 3,
  url: `https://www.vlr.gg/${754730 + i}/`,
  sides: [0, 1].map((side) => ({
    team_id: i * 2 + side + 1,
    name: names[i * 2 + side],
    logo: null,
    tag: null,
    matches: 10,
    p_win: side === 0 ? 0.6 : 0.4,
  })),
  market: null,
}));
const schedule = [
  [754734, "Upper Semifinals"], [754735, "Upper Semifinals"], [754736, "Upper Final"],
  [754738, "Lower Round 1"], [754739, "Lower Round 1"],
  [754740, "Lower Round 2"], [754741, "Lower Round 2"], [754742, "Lower Round 3"],
  [754743, "Lower Final"], [754737, "Grand Final"],
].map(([match_id, stage]) => ({ match_id, stage, start: null, best_of: 3 }));

const payload = { opening, schedule };

test("maps the complete 14-match schedule and keeps every inferred edge unconfirmed", () => {
  const graph = buildBracketGraph(payload);
  assert.equal(graph.nodes.length, 14);
  assert.equal(graph.edges.length, 20);
  assert.deepEqual(graph.unmapped, []);
  assert.ok(graph.edges.every((edge) => edge.confirmed === false));
  assert.equal(graph.byId.get(754734).feeds.length, 2);
  assert.equal(graph.byId.get(754734).feeds[0].take, "winner");
  assert.equal(graph.byId.get(754738).feeds[0].take, "loser");
  assert.equal(graph.byId.get(754737).feeds[0].from, 754736);
});

test("does not draw edges through missing source or destination slots", () => {
  const graph = buildBracketGraph({ opening, schedule: schedule.filter((slot) => slot.match_id !== 754734) });
  assert.equal(graph.nodes.length, 13);
  assert.ok(graph.edges.every((edge) => edge.from !== 754734 && edge.to !== 754734));
  assert.equal(graph.unmapped.length, 0);
});

test("keeps only valid forecast flows and uses strict favourite comparison", () => {
  const matches = structuredClone(opening);
  matches[0].sides[0].p_win = 0.5;
  matches[0].sides[1].p_win = 0.5;
  matches[1].sides[0].p_win = Number.NaN;
  matches[2].sides[1].p_win = null;
  const graph = buildBracketGraph({ opening: matches, schedule });
  const qf1 = graph.flows.filter((flow) => flow.nodeId === 754730);
  assert.equal(qf1.length, 2);
  assert.ok(qf1.every((flow) => flow.favourite === false));
  assert.equal(graph.flows.filter((flow) => flow.nodeId === 754731).length, 1);
  assert.equal(graph.flows.find((flow) => flow.nodeId === 754731).teamId, 4);
  assert.equal(graph.flows.filter((flow) => flow.nodeId === 754732).length, 1);
});

test("reports slots absent from the known topology instead of inventing nodes", () => {
  const graph = buildBracketGraph({ opening, schedule: [...schedule, { match_id: 999999, stage: "New round", start: null, best_of: 3 }] });
  assert.deepEqual(graph.unmapped, [999999]);
  assert.equal(graph.nodes.some((node) => node.id === 999999), false);
});

test("splits progression edges (drawn) from loser drop-ins (labels only)", () => {
  const graph = buildBracketGraph(payload);
  const prog = progressionEdges(graph.edges), drops = dropInEdges(graph.edges);
  assert.equal(prog.length + drops.length, graph.edges.length);
  assert.equal(prog.length, 13);
  assert.equal(drops.length, 7);
  assert.ok(prog.every((e) => e.take === "winner"));
  assert.ok(drops.every((e) => e.take === "loser"));
  // UQF1 loser lands in LR1-1; Upper Final loser lands in the Lower Final; Grand Final and Lower Final drop nobody.
  assert.deepEqual(dropTargets(graph, 754730).map((e) => e.to), [754738]);
  assert.deepEqual(dropTargets(graph, 754736).map((e) => e.to), [754743]);
  assert.deepEqual(dropTargets(graph, 754737), []);
  assert.deepEqual(dropTargets(graph, 754743), []);
});
