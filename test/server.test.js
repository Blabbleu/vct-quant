/**
 * Smallest check that fails if the backend breaks: boot it, hit every route.
 *
 *   npm run check          # needs the database: vct init-db && vct update
 */
const assert = require("node:assert/strict");
const { server, ROUTES } = require("../server.js");

async function main() {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    for (const route of Object.keys(ROUTES)) {
      const resp = await fetch(base + route);
      assert.equal(resp.status, 200, `${route} answered ${resp.status}`);
      assert.match(resp.headers.get("content-type"), /application\/json/);
      const body = await resp.json();
      assert.ok(body && (typeof body === "object"), `${route} returned no payload`);
      console.log(`  ${route} ok`);
    }

    const snapshot = await (await fetch(base + "/api/snapshot")).json();
    for (const key of ["coverage", "backtest", "gc", "live", "fixtures", "rankings", "ledger"]) {
      assert.ok(key in snapshot, `snapshot is missing ${key}`);
    }
    assert.ok(snapshot.backtest.log_loss > 0.3 && snapshot.backtest.log_loss < 0.7,
      `implausible log loss ${snapshot.backtest.log_loss}`);

    // Live breakdown by pool: pools partition the graded log, buckets fold to the favourite.
    if (snapshot.live.graded > 0) {
      const pools = snapshot.live.by_tier?.tiers;
      assert.ok(Array.isArray(pools), "live.by_tier.tiers missing");
      assert.equal(pools.reduce((s, t) => s + t.n, 0), snapshot.live.graded);
      for (const t of pools) {
        const inBuckets = t.buckets.reduce((s, b) => s + b.n, 0);
        assert.equal(inBuckets, t.favourite.calls);
        assert.equal(inBuckets + t.coin_flips, t.n);
        for (const b of t.buckets) {
          if (b.n === 0) continue;
          assert.ok(b.predicted >= b.lo && b.predicted <= b.hi, `bucket ${b.lo} mean ${b.predicted}`);
          assert.ok(b.ci[0] <= b.actual && b.actual <= b.ci[1]);
        }
      }
    }

    const matchId = snapshot.fixtures[0]?.match_id;
    assert.ok(matchId, "snapshot needs a fixture for the Match Center check");
    const match = await fetch(base + `/api/match/${matchId}`);
    assert.equal(match.status, 200);
    const matchBody = await match.json();
    assert.equal(matchBody.match_id, matchId);
    assert.ok(Array.isArray(matchBody.points) && matchBody.points.length > 0);
    for (const side of ["a", "b"]) {
      assert.ok(Array.isArray(matchBody.recent_form?.[side]));
      assert.ok(matchBody.recent_form[side].length <= 5);
      for (const row of matchBody.recent_form[side]) {
        assert.ok(["W", "L"].includes(row.result));
        assert.ok(Date.parse(row.completed_at) < Date.parse(matchBody.points.at(-1).observed_at));
      }
    }
    assert.ok("result" in matchBody, "match payload must carry a result field (null until verified-finished)");
    if (matchBody.result) assert.ok(["verified", "unverified"].includes(matchBody.result.status));
    const h2h = matchBody.head_to_head;
    assert.ok(h2h && Array.isArray(h2h.series), "match payload must carry head_to_head");
    assert.equal(h2h.wins_a + h2h.wins_b, h2h.played);
    assert.ok(h2h.series.length <= Math.min(10, h2h.played));
    for (const row of h2h.series) {
      assert.ok(["a", "b"].includes(row.winner));
      assert.ok(row.match_id < matchId);
      assert.ok(Date.parse(row.completed_at) < Date.parse(matchBody.points.at(-1).observed_at));
    }
    // Every logged fixture's Match Center must answer, not 500 (NA slug regression).
    for (const fixture of snapshot.fixtures) {
      const r = await fetch(base + `/api/match/${fixture.match_id}`);
      assert.ok([200, 404].includes(r.status), `/api/match/${fixture.match_id} returned ${r.status}`);
      // Exact-score forecast: consistent with the series odds and the format, or withheld.
      if (fixture.scores !== null) {
        assert.equal(fixture.scores.length, fixture.best_of === 5 ? 6 : 4);
        const total = fixture.scores.reduce((s, row) => s + row.p, 0);
        assert.ok(Math.abs(total - 1) < 1e-6, `scores for ${fixture.match_id} sum to ${total}`);
        const wins = (fixture.best_of + 1) / 2;
        const aWins = fixture.scores.filter(row => row.score.startsWith(`${wins}-`))
          .reduce((s, row) => s + row.p, 0);
        assert.ok(Math.abs(aWins - fixture.p_a) < 1e-6, `score odds disagree with p_a for ${fixture.match_id}`);
      }
    }
    assert.equal((await fetch(base + "/api/match/0")).status, 404);
    assert.equal((await fetch(base + "/api/match/999999999")).status, 404);
    assert.equal((await fetch(base + "/api/match/1%2F2")).status, 404);
    console.log("  /api/match/:id movement and unknown IDs ok");

    const team = await fetch(base + "/api/team/4529");
    assert.equal(team.status, 200);
    const teamBody = await team.json();
    assert.equal(teamBody.team_id, 4529);
    assert.ok(Array.isArray(teamBody.results));
    assert.equal((await fetch(base + "/api/team/0")).status, 404);
    assert.equal((await fetch(base + "/api/team/999999999")).status, 404);
    assert.equal((await fetch(base + "/api/team/1%2F2")).status, 404);
    console.log("  /api/team/:id identity and unknown IDs ok");

    const player = await fetch(base + "/api/player/9801");
    assert.equal(player.status, 200);
    const playerBody = await player.json();
    assert.equal(playerBody.player_id, 9801);
    assert.ok(playerBody.recorded_maps > 0 && playerBody.maps.length <= 20);
    assert.ok(Array.isArray(playerBody.agents) && Array.isArray(playerBody.teams));
    assert.equal((await fetch(base + "/api/player/0")).status, 404);
    assert.equal((await fetch(base + "/api/player/999999999")).status, 404);
    assert.equal((await fetch(base + "/api/player/1%2F2")).status, 404);
    console.log("  /api/player/:id exact identity and unknown IDs ok");

    const champions = await fetch(base + "/api/champions/2766");
    assert.equal(champions.status, 200);
    const championsBody = await champions.json();
    assert.equal(championsBody.event_id, 2766);
    assert.deepEqual(championsBody.groups.C.expected.winners, [11058, 624]);
    assert.deepEqual(championsBody.groups.D.expected.winners, [8877, 1034]);
    assert.equal(championsBody.title_odds, null);
    assert.equal(championsBody.groups.C.entrants[11058], "G2 Esports");
    assert.equal(championsBody.groups.C.slots.decider.match_id, 753458);
    for (const [letter, group] of Object.entries(championsBody.groups)) {
      const q = group.qualification;
      assert.ok(q, `group ${letter} lacks a qualification block`);
      if (q.withheld) continue;
      const sum = q.teams.reduce((s, t) => s + t.p_qualify, 0);
      const first = q.teams.reduce((s, t) => s + t.p_first, 0);
      assert.ok(Math.abs(sum - 2) < 1e-9 && Math.abs(first - 1) < 1e-9, `group ${letter} odds do not sum to 2/1`);
      for (const t of q.teams) if (t.qualified) assert.ok(Math.abs(t.p_qualify - 1) < 1e-12);
    }
    assert.equal((await fetch(base + "/api/champions/0")).status, 404);
    assert.equal((await fetch(base + "/api/champions/2767")).status, 404);
    console.log("  /api/champions/2766 source-pinned group status ok");

    const paper = await fetch(base + "/api/paper-ledger");
    assert.equal(paper.status, 200);
    const paperBody = await paper.json();
    assert.ok(Array.isArray(paperBody.rows));
    assert.equal(paperBody.n, paperBody.rows.length);
    assert.ok(paperBody.rows.every(r => r.return_per_unit == null || r.status === "settled"));
    console.log("  /api/paper-ledger frozen entries ok");

    const results = await fetch(base + "/api/results");
    assert.equal(results.status, 200);
    const resultsBody = await results.json();
    assert.ok(Array.isArray(resultsBody.rows));
    assert.equal(resultsBody.verified + resultsBody.unverified, resultsBody.rows.length);
    for (const row of resultsBody.rows) {
      assert.ok(Date.parse(row.forecast_at) < Date.parse(row.scheduled_at), `${row.match_id} forecast after start`);
      assert.ok(["verified", "unverified"].includes(row.result.status));
      if (row.result.status !== "verified") assert.equal(row.log_loss, null);
      else assert.ok(row.log_loss > 0 && ["a", "b"].includes(row.result.winner));
    }
    console.log(`  /api/results ${resultsBody.rows.length} finished logged fixtures ok`);

    // A team in a finished Tier-1 logged fixture sees the same call from its side.
    const tier1 = resultsBody.rows.find(r => r.tier === 1 && r.result.status === "verified" && r.team_a_id);
    const quiet = await (await fetch(base + "/api/team/4529")).json();
    assert.ok(Array.isArray(quiet.logged_results.rows));
    if (tier1) {
      const own = await (await fetch(base + `/api/team/${tier1.team_a_id}`)).json();
      const mine = own.logged_results.rows.find(r => r.match_id === tier1.match_id);
      assert.ok(mine, `team ${tier1.team_a_id} lacks logged match ${tier1.match_id}`);
      assert.ok(Math.abs(mine.p_win - tier1.p_a) < 1e-12);
      assert.equal(mine.won, tier1.result.winner === "a");
      assert.equal(mine.maps_for, tier1.result.maps_a);
      assert.ok(own.logged_results.rows.every(r => r.status === "verified" || r.log_loss === null));
      console.log(`  /api/team/${tier1.team_a_id} logged results agree with /api/results ok`);
    }

    const ops = await fetch(base + "/api/ops");
    assert.equal(ops.status, 200);
    const opsBody = await ops.json();
    assert.ok(["ok", "degraded", "stale", "unknown"].includes(opsBody.matchday.status));
    assert.ok(Array.isArray(opsBody.matchday.recent_runs));
    for (const key of ["events", "event_matches", "upcoming", "match_details", "polymarket"]) {
      assert.ok(key in opsBody.sources, `ops sources missing ${key}`);
    }
    assert.ok(opsBody.prediction_log.rows >= 0 && "database" in opsBody);
    console.log(`  /api/ops matchday ${opsBody.matchday.status} ok`);

    // Every page route returns an HTML shell; the client router renders it.
    // With web/dist built that is the multipage app, otherwise the legacy desk.
    for (const pagePath of ["/", "/matches", "/results", `/match/${matchId}`, `/team/${teamBody.team_id}`, `/player/${playerBody.player_id}`, "/champions/2766", "/rankings", "/edge", "/track-record", "/about", "/status"]) {
      const page = await fetch(base + pagePath);
      assert.equal(page.status, 200, `${pagePath} answered ${page.status}`);
      assert.match(page.headers.get("content-type"), /text\/html/);
      assert.match(await page.text(), /<div id="root">|VCT Quant Desk/);
    }
    console.log("  page routes serve the app shell");

    const legacy = await fetch(base + "/legacy");
    assert.equal(legacy.status, 200);
    assert.match(await legacy.text(), /VCT Quant Desk/);
    console.log("  /legacy serves the original single-file desk");

    assert.equal((await fetch(base + "/logos/0.png")).status, 404);
    assert.equal((await fetch(base + "/logos/..%2Fteam_logos.json")).status, 404);
    assert.equal((await fetch(base + "/logos/1.exe")).status, 404);
    console.log("  /logos only serves numeric image files");

    assert.equal((await fetch(base + "/api/nope")).status, 404);
    assert.equal((await fetch(base + "/assets/missing.js")).status, 404);
    assert.equal((await fetch(base + "/assets/..%2F..%2Fserver.js")).status, 404);
    assert.equal((await fetch(base + "/api/snapshot", { method: "POST" })).status, 405);
    console.log("  unknown API/asset 404, traversal blocked, read-only 405 ok");
    console.log("all checks passed");
  } finally {
    server.close();
  }
}

main().catch(err => { console.error(err.message); process.exitCode = 1; });
