import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { homeEmptyLine } from '../src/lib/homeCopy.ts';

test('home empty state explains when Tier 1 forecasts resume', () => {
  assert.equal(homeEmptyLine(0), 'No Tier 1 match is scheduled yet. Forecasts resume when the next Tier 1 fixtures are published.');
});

test('Champions quick link uses current playoffs copy', async () => {
  const home = await readFile(new URL('../src/pages/Home.tsx', import.meta.url), 'utf8');
  assert.match(home, /title: "Champions Shanghai", line: "Playoff bracket, title odds and verified results\."/);
  assert.doesNotMatch(home, /Champions Shanghai groups/);
});
