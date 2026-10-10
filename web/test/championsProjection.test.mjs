import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeCandidates, mostLikely, titleTable } from '../src/lib/championsProjection.ts';

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
