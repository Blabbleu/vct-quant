import test from 'node:test';
import assert from 'node:assert/strict';
import { championOf, isEliminated, isPrecedentProjection, mergeCandidates, mostLikely, routingChip, slotBasis, titleTable } from '../src/lib/championsProjection.ts';

const side = (team_id, name) => ({ team_id, name, logo: `${name}.png`, tag: name.slice(0, 3), matches: 1, p_win: null });
const final = (sides = [side(1, 'Alpha'), side(2, 'Bravo')], result = { winner_team_id: 1, scores: [3, 1] }, extras = {}) => ({
  schedule: [{ match_id: 754737, stage: 'Grand Final', sides, result, ...extras }], unverified_match_ids: [],
});

test('championOf returns verified Grand Final winner with winner-first positional scores', () => {
  assert.deepEqual(championOf(final()), { team_id: 1, name: 'Alpha', logo: 'Alpha.png', tag: 'Alp', scores: [3, 1] });
  assert.deepEqual(championOf(final([side(2, 'Bravo'), side(1, 'Alpha')], { winner_team_id: 1, scores: [1, 3] })), {
    team_id: 1, name: 'Alpha', logo: 'Alpha.png', tag: 'Alp', scores: [3, 1],
  });
});

test('championOf rejects absent, unverified, or inconsistent Grand Final results', () => {
  assert.equal(championOf({ schedule: [], unverified_match_ids: [] }), null);
  assert.equal(championOf(final([side(1, 'Alpha'), side(2, 'Bravo')], null)), null);
  assert.equal(championOf({ ...final(), unverified_match_ids: [754737] }), null);
  assert.equal(championOf(final([side(1, 'Alpha'), side(2, 'Bravo')], { winner_team_id: 3, scores: [3, 1] })), null);
  assert.equal(championOf(final([side(1, 'Alpha'), side(2, 'Bravo')], { winner_team_id: 1, scores: [2, 2] })), null);
  assert.equal(championOf(final([side(1, 'Alpha'), side(2, 'Bravo')], { winner_team_id: 1, scores: [1, 3] })), null);
  assert.equal(championOf(final([side(1, 'Alpha')], { winner_team_id: 1, scores: [3, 1] })), null);
  assert.equal(championOf(undefined), null);
});

test('slotBasis safely reads observed and precedent routing by stringified match ID', () => {
  const projection = { routing_basis: { slots: { '754734': 'observed', '754736': 'precedent', '754737': 'unknown' } } };
  assert.equal(slotBasis(projection, 754734), 'observed');
  assert.equal(slotBasis(projection, '754736'), 'precedent');
  assert.equal(slotBasis(projection, 754737), null);
  assert.equal(slotBasis(projection, 754738), null);
  assert.equal(slotBasis({ withheld: 'routing unresolved' }, '754736'), null);
  assert.equal(slotBasis({}, '754736'), null);
  assert.equal(slotBasis({ routing_basis: {} }, '754736'), null);
  assert.equal(slotBasis(null, '754736'), null);
});

test('isPrecedentProjection requires an unnamed unplayed slot, a candidate, and precedent basis', () => {
  const node = { id: 42 };
  const projection = {
    slots: { '42': { candidates: [{ team_ids: [1, 2], p_pairing: 0.8, p_a: 0.6 }] } },
    routing_basis: { slots: { '42': 'precedent' } },
  };
  assert.equal(isPrecedentProjection(node, projection), true);
  assert.equal(isPrecedentProjection(node, { ...projection, routing_basis: { slots: { '42': 'observed' } } }), false);
  assert.equal(isPrecedentProjection({ ...node, sides: [] }, projection), false);
  assert.equal(isPrecedentProjection({ ...node, result: {} }, projection), false);
  assert.equal(isPrecedentProjection(node, { ...projection, slots: { '42': { candidates: [] } } }), false);
  assert.equal(isPrecedentProjection(node, { withheld: 'routing unresolved' }), false);
  assert.equal(isPrecedentProjection(node, null), false);
});

test('isEliminated is true only when title probability is zero', () => {
  assert.equal(isEliminated({ p_title: 0 }), true);
  assert.equal(isEliminated({ p_title: 0.0001 }), false);
  assert.equal(isEliminated({}), false);
});

test('merges oriented candidates into unordered pairs and reweights p_a', () => {
  const merged = mergeCandidates({ candidates: [
    { team_ids: [1034, 11058], p_pairing: 0.151, p_a: 0.551 },
    { team_ids: [11058, 1034], p_pairing: 0.138, p_a: 0.449 },
  ] });
  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0].team_ids, [1034, 11058]);
  assert.ok(Math.abs(merged[0].p_pairing - 0.289) < 1e-9);
  assert.ok(Math.abs(merged[0].p_a - ((0.151 * 0.551 + 0.138 * (1 - 0.449)) / 0.289)) < 1e-9);
});

test('sorts merged candidates by pairing probability', () => {
  const got = mergeCandidates({ candidates: [
    { team_ids: [1, 2], p_pairing: 0.2, p_a: 0.6 },
    { team_ids: [3, 4], p_pairing: 0.8, p_a: 0.4 },
  ] });
  assert.deepEqual(got.map(x => x.team_ids), [[3, 4], [1, 2]]);
  assert.equal(mostLikely({ candidates: [] }), null);
});

test('missing candidates and withheld projections are safe', () => {
  assert.deepEqual(mergeCandidates(undefined), []);
  assert.deepEqual(mergeCandidates(null), []);
  assert.deepEqual(mergeCandidates({}), []);
  assert.deepEqual(mergeCandidates({ candidates: [] }), []);
  assert.equal(mostLikely(undefined), null);
  assert.deepEqual(titleTable({ withheld: 'routing unresolved' }), []);
});

test('routing chip reflects published projection availability', () => {
  assert.equal(routingChip({ routing: 'unresolved' }), 'ROUTING UNCONFIRMED');
  assert.equal(routingChip({ routing: 'projected', projection: { withheld: 'routing unresolved' } }), 'ROUTING UNCONFIRMED');
  assert.equal(routingChip({ routing: 'projected' }), 'ROUTING UNCONFIRMED');
  assert.equal(routingChip({ routing: 'projected', projection: { slots: {}, routing_basis: { slots: { LR: 'precedent' } } } }), 'PROJECTED ROUTING');
});

test('title table validates probabilities, defaults reach values, and sorts deterministically', () => {
  const rows = titleTable({ teams: [
    { team_id: 9, p_title: 0.4, p_reach: { GF: 0.7 } },
    { team_id: 4, p_title: 0.4, p_reach: { GF: 0.7 } },
    { team_id: 5, p_title: 0.4, p_reach: { GF: 0.8 } },
    { team_id: 3, p_title: 0, p_reach: {} },
    { team_id: 10, p_title: 0.8, p_reach: { GF: Infinity } },
    { team_id: 11, p_title: NaN, p_reach: {} },
    { team_id: 12, p_title: Infinity, p_reach: {} },
    { team_id: 13, p_title: -0.1, p_reach: {} },
    { team_id: 14, p_title: 1.1, p_reach: {} },
  ] });
  assert.deepEqual(rows.map(row => row.team_id), [10, 5, 4, 9, 3]);
  assert.equal(rows.find(row => row.team_id === 10).p_grand_final, 0);
  assert.equal(rows.find(row => row.team_id === 10).p_upper_final, 0);
});

test('title table keeps teams with absent or null reach data and reads long keys and aliases', () => {
  const rows = titleTable({ teams: [
    { team_id: 1, p_title: 0.2 },
    { team_id: 2, p_title: 0.1, p_reach: null },
    { team_id: 3, p_title: 0.4, p_reach: { 'Upper Final': 0.3, UF: 0.2, 'Grand Final': 0.15, GF: 0.1 } },
    { team_id: 4, p_title: 0.3, p_reach: { UF: 0.25, GF: 0.12 } },
  ] });
  assert.deepEqual(rows.map(row => row.team_id), [3, 4, 1, 2]);
  assert.deepEqual(rows.filter(row => row.team_id <= 2).map(row => [row.p_upper_final, row.p_grand_final]), [[0, 0], [0, 0]]);
  assert.deepEqual(rows.filter(row => row.team_id >= 3).map(row => [row.p_upper_final, row.p_grand_final]), [[0.3, 0.15], [0.25, 0.12]]);
});
