import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeCandidates, mostLikely, routingChip, titleTable } from '../src/lib/championsProjection.ts';

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
