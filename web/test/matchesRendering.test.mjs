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
  const source = fs.readFileSync(new URL("../src/components/matches/MatchesView.tsx", import.meta.url), "utf8");
  assert.match(source, /<JustFinished\s+results=\{results\}\s*\/>/);
});

test("Matches page renders the extracted MatchesView", () => {
  const source = fs.readFileSync(new URL("../src/pages/Matches.tsx", import.meta.url), "utf8");
  assert.match(source, /<MatchesView\s/);
});

test("isChampionsEvent matches only canonical Valorant Champions titles", async () => {
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: "/tmp/vct-quant-vite-test", server: { middlewareMode: true } });
  try {
    const { isChampionsEvent } = await vite.ssrLoadModule("/src/lib/matchesData.ts");
    assert.equal(isChampionsEvent("Valorant Champions 2026"), true);
    assert.equal(isChampionsEvent("Valorant Champions 2027"), true);
    assert.equal(isChampionsEvent("Game Changers 2026: Championship São Paulo"), false);
    assert.equal(isChampionsEvent("Champions Tour 2026"), false);
    assert.equal(isChampionsEvent(""), false);
    assert.equal(isChampionsEvent(null), false);
  } finally { await vite.close(); }
});

const fixture = (id, event, tier, start) => ({
  match_id: id, start, event, series: "Playoffs: Round 1", tier, best_of: 3,
  team_a: `Team ${id} A`, team_b: `Team ${id} B`, logo_a: null, logo_b: null,
  tag_a: null, tag_b: null, elo_a: 1500, elo_b: 1490, p_a: 0.55, p_sweep: null,
  scores: null, matches_a: 0, matches_b: 0, market: null, spread: null, volume: null, url: "#",
});
const playoffStage = (match_id, stage, start, day = start) => ({
  match_id, stage, start, played_on: day, best_of: 3, url: null,
  sides: [{ team_id: match_id * 2, name: "Alpha", logo: null, tag: "ALP", matches: 3, p_win: 0.6 },
    { team_id: match_id * 2 + 1, name: "Bravo", logo: null, tag: "BRV", matches: 3, p_win: 0.4 }],
  market: null, result: { winner_team_id: match_id * 2, scores: [2, 0] },
});
const snapshot = fixtures => ({
  fixtures, rankings: [], generated_at: "2026-10-15T00:00:00Z",
  coverage: { matches: 0, dated: 0, latest_result: "", tier_1: 0, tier_2: 0, tier_3: 0 },
  backtest: { n: 0, log_loss: 0, brier: 0, accuracy: 0, folds: [], calibration: [] },
  gc: { n: 0, log_loss: 0, k: 0, matches: 0 }, season: 2026, ledger: [],
  live: { logged: 0, graded: 0, rows: [], log_loss: null, brier: null, market: null, shadows: {} },
});
const championsState = (loading = false) => ({ data: { event_id: 2766, as_of: null, playoff_routing: "unresolved", title_odds: null,
  groups: { A: {}, B: {}, C: {}, D: {} }, playoffs: {
    routing: "unresolved", observed_at: "2026-10-15T00:00:00Z", sources: [],
    opening: [playoffStage(10, "Opening matches", "2026-10-07T10:00:00Z")],
    schedule: [playoffStage(11, "Upper Quarterfinals", "2026-10-09T10:00:00Z"), playoffStage(12, "Grand Final", "2026-10-18T10:00:00Z")],
  } }, error: null, loading });
const emptyResults = { data: { rows: [], verified: 0, unverified: 0, by_tier: {}, note: "" }, error: null, loading: false };

async function withMatchesView(run) {
  const originalNow = Date.now;
  Date.now = () => FIXED_NOW;
  const vite = await createServer({ configFile: false, plugins: [react()], cacheDir: "/tmp/vct-quant-vite-test", server: { middlewareMode: true } });
  try {
    const { default: MatchesView } = await vite.ssrLoadModule("/src/components/matches/MatchesView.tsx");
    const render = (fixtures, event = "all", champions = championsState()) => renderToStaticMarkup(
      React.createElement(MemoryRouter, null, React.createElement(MatchesView, {
        data: snapshot(fixtures), results: emptyResults, champions, event, setEvent() {},
      })),
    );
    await run(render);
  } finally { await vite.close(); Date.now = originalNow; }
}

const gcEvent = "Game Changers 2026: Championship São Paulo";
const gcFixtures = [22, 23, 24, 25].map((day, i) => fixture(i + 1, gcEvent, 3, `2026-10-${day}T12:00:00Z`));

test("GC hero uses tier 3 facts without Champions timeline or bracket", async () => withMatchesView(render => {
  const html = render(gcFixtures);
  const facts = html.match(/<div class="event-hero-facts num">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(facts, /Game Changers/);
  assert.doesNotMatch(facts, /Tier 1/);
  assert.doesNotMatch(html, /class="event-stage|Oct 7|Oct 18/);
  assert.doesNotMatch(html, /Champions bracket/);
}));

test("GC hero omits Champions timeline and bracket loading markup", async () => withMatchesView(render => {
  const html = render(gcFixtures, "all", championsState(true));
  assert.doesNotMatch(html, /event-stages-skel|Champions bracket|rail-skel/);
}));

test("real Champions event retains tier, timeline and bracket", async () => withMatchesView(render => {
  const html = render([fixture(30, "Valorant Champions 2026", 1, "2026-10-22T12:00:00Z")]);
  const facts = html.match(/<div class="event-hero-facts num">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(facts, /Tier 1/);
  assert.match(html, /Opening matches/);
  assert.match(html, /Champions bracket/);
}));

test("all-event hero follows the next event for GC and Champions fixtures", async () => withMatchesView(render => {
  const gcFirst = [fixture(41, "Valorant Champions 2026", 1, "2026-10-23T12:00:00Z"), ...gcFixtures];
  const gcHtml = render(gcFirst);
  const gcFacts = gcHtml.match(/<div class="event-hero-facts num">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(gcFacts, /Game Changers/);
  assert.doesNotMatch(gcHtml, /Opening matches|Champions bracket/);

  const championsFirst = [fixture(51, "Valorant Champions 2026", 1, "2026-10-21T12:00:00Z"), ...gcFixtures];
  const championsHtml = render(championsFirst);
  assert.match(championsHtml, /Opening matches/);
  assert.match(championsHtml, /Champions bracket/);
}));
