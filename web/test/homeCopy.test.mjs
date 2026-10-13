import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fixtureTierCopy, homeEmptyLine, homeHeadlineCopy } from '../src/lib/homeCopy.ts';

const fixture = (tier, start = '2026-10-12T12:00:00Z') => ({ tier, start });

test('home headline and lede describe the off-season when there are no fixtures', () => {
  const copy = homeHeadlineCopy([]);
  assert.equal(copy.headline, 'The desk is between scheduled Tier 1 matches');
  assert.equal(copy.lede, 'Forecasts resume when Tier 1 fixtures are published.');
  assert.doesNotMatch(`${copy.headline} ${copy.lede}`, /next VCT match|upcoming Tier 1 match|2027|winner/i);
});

test('Tier 1-only home copy remains exact', () => {
  assert.deepEqual(homeHeadlineCopy([fixture(1)]), {
    headline: 'Who wins the next VCT match?',
    lede: 'Win chances for every upcoming Tier 1 match, next to what the betting market thinks, and an honest record of how the model has done.',
  });
});

test('Home selects its headline copy from fixture availability', async () => {
  const home = await readFile(new URL('../src/pages/Home.tsx', import.meta.url), 'utf8');
  assert.match(home, /homeHeadlineCopy\(data\.fixtures\)/);
  assert.match(home, /<Words text=\{headlineCopy\.headline\} \/>/);
  assert.match(home, /\{headlineCopy\.lede\}/);
});

test('home names only the tiers in the slate and headlines the earliest fixture tier', () => {
  const gcOnly = homeHeadlineCopy([fixture(3)]);
  assert.match(gcOnly.headline, /Game Changers/);
  assert.match(gcOnly.lede, /Game Changers/);
  assert.doesNotMatch(gcOnly.lede, /Tier 1/);
  const gcFirst = homeHeadlineCopy([fixture(3, '2026-10-12T10:00:00Z'), fixture(1)]);
  assert.match(gcFirst.headline, /Game Changers/);
  assert.match(gcFirst.lede, /Tier 1 and Game Changers/);
  const tierOneFirst = homeHeadlineCopy([fixture(3), fixture(1, '2026-10-12T09:00:00Z')]);
  assert.match(tierOneFirst.headline, /Tier 1/);
  assert.match(tierOneFirst.lede, /Tier 1 and Game Changers/);
  assert.match(homeHeadlineCopy([fixture(2)]).lede, /Tier 2/);
  assert.doesNotMatch(homeHeadlineCopy([fixture(2)]).lede, /Tier 1|Game Changers/);
  assert.match(homeHeadlineCopy([fixture(2), fixture(3)]).lede, /Tier 2 and Game Changers/);
  assert.match(homeHeadlineCopy([fixture(1), fixture(2), fixture(3)]).lede, /Tier 1, Tier 2 and Game Changers/);
});

test('home empty state explains when Tier 1 forecasts resume', () => {
  assert.equal(homeEmptyLine(0), 'No Tier 1 match is scheduled yet. Forecasts resume when the next Tier 1 fixtures are published.');
});

test('empty fixture tier copy does not invent Tier 1', () => {
  assert.equal(fixtureTierCopy([]), '');
});

test('Champions quick link uses current playoffs copy', async () => {
  const home = await readFile(new URL('../src/pages/Home.tsx', import.meta.url), 'utf8');
  assert.match(home, /title: "Champions Shanghai", line: "Playoff bracket, title odds and verified results\."/);
  assert.doesNotMatch(home, /Champions Shanghai groups/);
});

test('Matches derives tier labels from the displayed fixture selection', async () => {
  const matches = await readFile(new URL('../src/pages/Matches.tsx', import.meta.url), 'utf8');
  assert.match(matches, /fixtureTierCopy\(shown\)/);
  assert.match(matches, /All \{fixtureTierCopy\(fixtures\)\}/);
  assert.match(matches, /Show all \{fixtureTierCopy\(fixtures\)\}/);
  assert.match(matches, /Upcoming \{shownTierCopy\} matches grouped by day/);
});
