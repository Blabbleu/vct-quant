import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";

test("BracketMini renders distinct completed and unpublished empty states", async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: "/tmp/vct-quant-vite-test", server: { middlewareMode: true } });
  try {
    const { BracketMini } = await vite.ssrLoadModule("/src/components/matches/RailPanels.tsx");
    const render = playoffs => renderToStaticMarkup(React.createElement(MemoryRouter, null,
      React.createElement(BracketMini, { playoffs, loading: false })));
    const noData = render(undefined);
    assert.match(noData, /Playoff data unavailable\./);
    const slot = (match_id, stage, sides, result) => ({ match_id, stage, start: null, best_of: 3, sides, result });
    const side = name => ({ team_id: 1, name, logo: null, tag: null, matches: null, p_win: null });
    const opening = Array.from({ length: 4 }, (_, i) => slot(i + 1, "Upper Quarterfinals", [side("A"), side("B")], { winner_team_id: 1, scores: [2, 0] }));
    const schedule = ["Upper Semifinals", "Lower Semifinals", "Final", "Grand Final"].map((stage, i) => slot(i + 5, stage, null, { winner_team_id: 1, scores: [2, 0] }));
    const completed = render({ opening, schedule });
    assert.match(completed, /All playoff matches are complete\./);
    assert.doesNotMatch(completed, /Upper Quarterfinals/);
    for (const playoffs of [
      { opening: [], schedule: [] },
      { opening: [slot(1, "Upper Quarterfinals", [side("TBD"), side("")], null)], schedule: [] },
      { opening, schedule: schedule.map((s, i) => i === 3 ? { ...s, result: null } : s) },
    ]) {
      assert.match(render(playoffs), /Playoff matchups not published yet\./);
    }
  } finally {
    await vite.close();
  }
});
