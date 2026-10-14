import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";

test("market quotes render liquidity status and subdued styling", async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: "/tmp/vct-quant-vite-test", server: { middlewareMode: true } });
  try {
    const { default: GapChip } = await vite.ssrLoadModule("/src/components/arena/GapChip.tsx");
    const { default: MatchRow } = await vite.ssrLoadModule("/src/components/arena/MatchRow.tsx");
    const renderGap = (props) => renderToStaticMarkup(React.createElement(GapChip, props));
    const low = renderGap({ model: 0.62, market: 0.5, spread: 0.04, volume: 8.19672 });
    assert.match(low, /Δ \+12\.0/);
    assert.match(low, /LOW VOLUME/);
    assert.doesNotMatch(low, /AGREE|BIG GAP/);
    for (const [volume, label] of [[8, "LOW VOLUME"], [null, "UNTRUSTED PRICE"]]) {
      const html = renderGap({ model: 0.62, market: 0.5, spread: 0.04, volume });
      assert.match(html, /Δ \+12\.0/);
      assert.match(html, new RegExp(label));
      assert.doesNotMatch(html, /AGREE|BIG GAP/);
    }
    assert.match(renderGap({ model: 0.62, market: 0.5, spread: 0.1, volume: 1000 }), /BIG GAP/);
    assert.match(renderGap({ model: 0.62, market: 0.5, spread: 0.1001, volume: 1000 }), /WIDE SPREAD/);

    const fixture = {
      match_id: 766310, start: "2026-10-15T12:00:00Z", event: "VCT", series: "Playoffs", tier: 1, best_of: 3,
      team_a: "Team A", team_b: "Team B", logo_a: null, logo_b: null, tag_a: "AAA", tag_b: "BBB",
      elo_a: 1500, elo_b: 1490, p_a: 0.55, p_sweep: null, scores: null, matches_a: 10, matches_b: 10,
      market: 0.43, spread: 0.04, volume: 8.19672, url: "",
    };
    const row = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(MatchRow, { f: fixture, detail: false })));
    assert.equal((row.match(/class="muted">(?:43\.0|57\.0)<\/span>/g) ?? []).length, 2);
    assert.doesNotMatch(row, /class="match-row-market-value">(?:43\.0|57\.0)/);
    assert.match(row, /LOW VOLUME/);
    assert.match(row, /Δ \+12\.0/);
    assert.doesNotMatch(row, /AGREE|BIG GAP/);
  } finally {
    await vite.close();
  }
});
