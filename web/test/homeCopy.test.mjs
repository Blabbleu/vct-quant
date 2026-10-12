import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { homeEmptyLine, homeHeadlineCopy } from '../src/lib/homeCopy.ts';

test('home headline and lede describe the off-season when there are no fixtures', () => {
  const copy = homeHeadlineCopy(false);
  assert.equal(copy.headline, 'The desk is between scheduled Tier 1 matches');
  assert.equal(copy.lede, 'Forecasts resume when Tier 1 fixtures are published.');
  assert.doesNotMatch(`${copy.headline} ${copy.lede}`, /next VCT match|upcoming Tier 1 match|2027|winner/i);
});

test('home headline and lede preserve the scheduled-fixture copy exactly', () => {
  assert.deepEqual(homeHeadlineCopy(true), {
    headline: 'Who wins the next VCT match?',
    lede: 'Win chances for every upcoming Tier 1 match, next to what the betting market thinks, and an honest record of how the model has done.',
  });
});

test('Home selects its headline copy from fixture availability', async () => {
  const home = await readFile(new URL('../src/pages/Home.tsx', import.meta.url), 'utf8');
  assert.match(home, /homeHeadlineCopy\(data\.fixtures\.length > 0\)/);
  assert.match(home, /<Words text=\{headlineCopy\.headline\} \/>/);
  assert.match(home, /\{headlineCopy\.lede\}/);
});

test('home empty state explains when Tier 1 forecasts resume', () => {
  assert.equal(homeEmptyLine(0), 'No Tier 1 match is scheduled yet. Forecasts resume when the next Tier 1 fixtures are published.');
});

test('Champions quick link uses current playoffs copy', async () => {
  const home = await readFile(new URL('../src/pages/Home.tsx', import.meta.url), 'utf8');
  assert.match(home, /title: "Champions Shanghai", line: "Playoff bracket, title odds and verified results\."/);
  assert.doesNotMatch(home, /Champions Shanghai groups/);
});
