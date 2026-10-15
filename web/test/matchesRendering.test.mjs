import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";

const FIXED_NOW = Date.parse("2026-10-15T12:00:00Z");
const row = (id, scheduled_at, team_a, team_b, status = "verified") => ({
  match_id: id, tier: 1, event: "Valorant Champions 2026", series: "Playoffs: Upper Quarterfinals", best_of: 3,
  scheduled_at, forecast_at: scheduled_at, team_a, team_b, team_a_key: team_a, team_b_key: team_b,
  team_a_id: id * 2, team_b_id: id * 2 + 1, logo_a: null, logo_b: null, tag_a: null, tag_b: null,
  p_a: 0.6, market_a: null, url: null, log_loss: 0.5, favourite_won: true,
  result: { status, reason: null, winner: status === "verified" ? "a" : null,
    maps_a: status === "verified" ? 2 : null, maps_b: status === "verified" ? 0 : null,
    maps: [], maps_complete: true, pre_start_winner_p: null, completed_on: scheduled_at, source_url: null, as_of: null },
});
const resultState = rows => ({ data: { rows, verified: rows.filter(r => r.result.status === "verified").length,
  unverified: rows.filter(r => r.result.status !== "verified").length, by_tier: {}, note: "" }, error: null, loading: false });

async function withComponent(run) {
  const originalNow = Date.now;
  Date.now = () => FIXED_NOW;
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: "/tmp/vct-quant-vite-test", server: { middlewareMode: true } });
  try {
    const { default: JustFinished } = await vite.ssrLoadModule("/src/components/matches/JustFinished.tsx");
    const render = props => renderToStaticMarkup(React.createElement(MemoryRouter, null,
      React.createElement(JustFinished, props)));
    await run(render);
  } finally {
    await vite.close();
    Date.now = originalNow;
  }
}

test("JustFinished renders only recent verified cards", async () => withComponent(render => {
  const html = render({ results: resultState([
    row(1, "2026-10-14T11:00:00Z", "Recent Alpha", "Recent Bravo"),
    row(2, "2026-10-14T09:00:00Z", "Recent Charlie", "Recent Delta"),
    row(3, "2026-10-11T11:00:00Z", "Old Echo", "Old Foxtrot"),
    row(4, "2026-10-11T09:00:00Z", "Old Golf", "Old Hotel"),
  ]) });
  assert.equal((html.match(/finished-card/g) ?? []).length, 2);
  for (const team of ["Recent Alpha", "Recent Bravo", "Recent Charlie", "Recent Delta"]) assert.match(html, new RegExp(team));
  for (const team of ["Old Echo", "Old Foxtrot", "Old Golf", "Old Hotel"]) assert.doesNotMatch(html, new RegExp(team));
}));

test("JustFinished gives the honest empty state when only old verified rows exist", async () => withComponent(render => {
  const html = render({ results: resultState([
    row(1, "2026-10-11T11:00:00Z", "Historical Alpha", "Historical Bravo"),
  ]) });
  assert.match(html, /No recent graded matches\./);
  assert.doesNotMatch(html, /finished-card/);
}));

test("JustFinished keeps the no graded matches copy for unverified-only rows", async () => withComponent(render => {
  const html = render({ results: resultState([row(1, "2026-10-14T11:00:00Z", "Pending Alpha", "Pending Bravo", "unverified")]) });
  assert.match(html, /No graded matches yet\./);
  assert.doesNotMatch(html, /finished-card/);
}));

test("JustFinished renders loading and error states", async () => withComponent(render => {
  const loading = render({ results: { data: null, error: null, loading: true } });
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /loading-card/);
  const error = render({ results: { data: null, error: "offline", loading: false } });
  assert.match(error, /Results unavailable right now \(offline\)\./);
}));

test("Matches page wires its results state into JustFinished", () => {
  const source = fs.readFileSync(new URL("../src/pages/Matches.tsx", import.meta.url), "utf8");
  assert.match(source, /<JustFinished\s+results=\{results\}\s*\/>/);
});
