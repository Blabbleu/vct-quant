import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

test('verified final renders only champion and runner-up in winner-first result order', async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: '/tmp/vct-quant-vite-test', server: { middlewareMode: true } });
  try {
    const [{ Standings }, { finalStandingsOf }] = await Promise.all([
      vite.ssrLoadModule('/src/pages/Champions.tsx'), vite.ssrLoadModule('/src/lib/championsProjection.ts'),
    ]);
    const playoffs = {
      routing: 'projected', observed_at: '2026-10-18T00:00:00Z', sources: [], opening: [], unverified_match_ids: [],
      schedule: [{
        match_id: 754737, stage: 'Grand Final', start: null, best_of: 5, url: null,
        sides: [
          { team_id: 2059, name: 'Team Vitality', logo: null, tag: 'VIT', matches: 0, p_win: null },
          { team_id: 6961, name: 'LOUD', logo: null, tag: 'LOUD', matches: 0, p_win: null },
        ],
        result: { winner_team_id: 6961, scores: [1, 3] },
      }],
    };
    const final = finalStandingsOf(playoffs);
    assert.deepEqual(final, {
      champion: { team_id: 6961, name: 'LOUD', logo: null, tag: 'LOUD', scores: [3, 1] },
      runnerUp: { team_id: 2059, name: 'Team Vitality', logo: null, tag: 'VIT', scores: [1, 3] },
    });
    const html = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Standings, {
      playoffs,
      oddsRows: [
        { team_id: 6961, p_title: 1, p_grand_final: 1 },
        { team_id: 2059, p_title: 0, p_grand_final: 0 },
        { team_id: 999, p_title: 0, p_grand_final: 0 },
      ],
      names: {},
    })));
    assert.match(html, /Final standings/);
    assert.match(html, /FINAL/);
    const championPos = html.indexOf('Champion');
    const runnerPos = html.indexOf('Runner-up');
    assert.ok(championPos >= 0 && runnerPos > championPos);
    assert.match(html, /Champion<\/b><small>Won Grand Final 3–1/);
    assert.match(html, /Runner-up<\/b><small>Lost Grand Final 1–3/);
    assert.equal((html.match(/href="\/team\//g) ?? []).length, 2);
    assert.doesNotMatch(html, /P\(title\)|P\(reach Grand Final\)|Eliminated|100\.0%|999/);
  } finally {
    await vite.close();
  }
});

test('unverified and unfinished finals retain projected title odds without asserting placements', async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: '/tmp/vct-quant-vite-test', server: { middlewareMode: true } });
  try {
    const [{ Standings }, { finalStandingsOf, titleTable }] = await Promise.all([
      vite.ssrLoadModule('/src/pages/Champions.tsx'), vite.ssrLoadModule('/src/lib/championsProjection.ts'),
    ]);
    const finalRow = {
      match_id: 754737, stage: 'Grand Final', start: null, best_of: 5, url: null,
      sides: [
        { team_id: 2059, name: 'Team Vitality', logo: null, tag: 'VIT', matches: 0, p_win: null },
        { team_id: 6961, name: 'LOUD', logo: null, tag: 'LOUD', matches: 0, p_win: null },
      ],
      result: { winner_team_id: 6961, scores: [1, 3] },
    };
    const oddsRows = titleTable({ teams: [
      { team_id: 6961, p_title: 1, p_reach: { GF: 1 } },
      { team_id: 2059, p_title: 0, p_reach: { GF: 0 } },
    ] });
    const render = playoffs => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Standings, {
      playoffs, oddsRows, names: { 6961: { name: 'LOUD', logo: null, tag: 'LOUD' }, 2059: { name: 'Team Vitality', logo: null, tag: 'VIT' } },
    })));
    for (const playoffs of [
      { routing: 'projected', observed_at: '', sources: [], opening: [], schedule: [finalRow], unverified_match_ids: [754737] },
      { routing: 'projected', observed_at: '', sources: [], opening: [], schedule: [{ ...finalRow, result: null }], unverified_match_ids: [] },
    ]) {
      assert.equal(finalStandingsOf(playoffs), null);
      const html = render(playoffs);
      assert.match(html, /PROJECTED/);
      assert.match(html, /P\(title\)/);
      assert.match(html, /Eliminated/);
      assert.doesNotMatch(html, /Champion|Runner-up|FINAL/);
    }
  } finally {
    await vite.close();
  }
});

test('finalStandingsOf returns null when verified winner has no runner-up side', async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: '/tmp/vct-quant-vite-test', server: { middlewareMode: true } });
  try {
    const { finalStandingsOf } = await vite.ssrLoadModule('/src/lib/championsProjection.ts');
    const playoffs = {
      schedule: [{ match_id: 1, stage: 'Grand Final', sides: [
        { team_id: 1, name: 'Winner', logo: null, tag: null },
      ], result: { winner_team_id: 1, scores: [3, 1] } }],
      unverified_match_ids: [],
    };
    assert.equal(finalStandingsOf(playoffs), null);
  } finally {
    await vite.close();
  }
});
