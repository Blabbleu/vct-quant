/**
 * Smallest check that fails if the backend breaks: boot it, hit every route.
 *
 *   npm run check          # needs the database: vct init-db && vct update
 */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const net = require("node:net");
const path = require("node:path");
const { server, ROUTES, createSnapshotter, createInFlight, createBoundedInFlight, computeSnapshot, modelFailurePayload } = require("../server.js");

assert.deepEqual(modelFailurePayload(), {
  error: "the model layer failed",
  hint: "run `vct init-db` and `vct update` first, or set PYTHON to your interpreter",
});
assert.equal("detail" in modelFailurePayload(), false,
  "public model errors must not expose subprocess details or local paths");

async function checkSnapshotSubprocessTimeout() {
  let options;
  const payload = await computeSnapshot((command, args, opts, callback) => {
    options = opts;
    callback(null, JSON.stringify({ ok: true }), "");
  });
  assert.deepEqual(payload, { ok: true });
  assert.equal(options.timeout, 120000,
    "a hung dashboard subprocess must be terminated after the bounded snapshot timeout");
  console.log("  dashboard subprocess has a bounded timeout");
}

async function checkSnapshotCacheRace() {
  let stamp = "old";
  let calls = 0;
  let releaseFirst;
  const get = createSnapshotter(
    async () => stamp,
    () => {
      calls += 1;
      if (calls === 1) return new Promise(resolve => { releaseFirst = resolve; });
      return { version: "new" };
    },
  );
  const firstRequest = get();
  while (!releaseFirst) await new Promise(resolve => setImmediate(resolve));
  stamp = "new";
  const concurrentRequest = get();
  releaseFirst({ version: "old" });
  assert.deepEqual(await firstRequest, { version: "new" });
  assert.deepEqual(await concurrentRequest, { version: "new" });
  assert.equal(calls, 2, "a request crossing a data update must recompute instead of caching stale data");
  assert.deepEqual(await get(), { version: "new" });
  assert.equal(calls, 2, "the verified snapshot should be cached");

  let failureStamp = "old";
  let rejectFirst;
  let failureCalls = 0;
  const recover = createSnapshotter(
    async () => failureStamp,
    () => {
      failureCalls += 1;
      if (failureCalls === 1) return new Promise((_, reject) => { rejectFirst = reject; });
      return { version: "recovered" };
    },
  );
  const staleRequest = recover();
  while (!rejectFirst) await new Promise(resolve => setImmediate(resolve));
  failureStamp = "new";
  const freshRequest = recover();
  rejectFirst(new Error("stale computation failed"));
  await assert.rejects(staleRequest, /stale computation failed/);
  assert.deepEqual(await freshRequest, { version: "recovered" });
  assert.equal(failureCalls, 2, "a failed stale computation must not block a fresh snapshot");
  console.log("  snapshot cache update race retries and caches the new payload");
}

async function checkInFlightDeduplication() {
  let calls = 0;
  const release = new Map();
  const get = createInFlight(key => {
    calls += 1;
    return new Promise(resolve => { release.set(key, () => resolve(key)); });
  });
  const first = get("team:42");
  const duplicate = get("team:42");
  const separate = get("team:43");
  assert.equal(calls, 2, "identical in-flight lookups should share one computation");
  release.get("team:42")();
  release.get("team:43")();
  assert.equal(await first, "team:42");
  assert.equal(await duplicate, "team:42");
  assert.equal(await separate, "team:43");
  const later = get("team:42");
  assert.equal(calls, 3, "completed results must not be cached");
  release.get("team:42")();
  assert.equal(await later, "team:42");
  console.log("  identical dynamic lookups share only in-flight work");
}

async function checkBoundedInFlight() {
  let active = 0;
  let maximum = 0;
  const release = new Map();
  const get = createBoundedInFlight(key => {
    active += 1;
    maximum = Math.max(maximum, active);
    return new Promise(resolve => {
      release.set(key, value => {
        active -= 1;
        resolve(value);
      });
    });
  }, 1, 1);
  const first = get("a");
  const queued = get("b");
  const duplicateQueued = get("b");
  await assert.rejects(get("c"), error => error.code === "OVERLOADED");
  while (!release.has("a")) await new Promise(resolve => setImmediate(resolve));
  assert.equal(maximum, 1, "active work must not exceed the configured limit");
  release.get("a")("A");
  assert.equal(await first, "A");
  while (!release.has("b")) await new Promise(resolve => setImmediate(resolve));
  release.get("b")("B");
  assert.equal(await queued, "B");
  assert.equal(await duplicateQueued, "B", "queued duplicate IDs should share one slot");
  assert.equal(maximum, 1);
  const later = get("c");
  while (!release.has("c")) await new Promise(resolve => setImmediate(resolve));
  release.get("c")("C");
  assert.equal(await later, "C", "overloaded work must not be retained; later requests can retry");
  assert.equal(maximum, 1);
  console.log("  distinct dynamic lookups have bounded concurrency and queueing");
}

async function checkInFlightFailureRetry() {
  let calls = 0;
  let rejectFirst;
  const get = createInFlight(() => {
    calls += 1;
    if (calls === 1) return new Promise((_, reject) => { rejectFirst = reject; });
    return Promise.resolve("recovered");
  });
  const first = get("player:7");
  const duplicate = get("player:7");
  assert.equal(calls, 1, "a failed in-flight computation should still be shared");
  rejectFirst(new Error("temporary failure"));
  await assert.rejects(first, /temporary failure/);
  await assert.rejects(duplicate, /temporary failure/);
  assert.equal(await get("player:7"), "recovered", "a rejection must be removed so later requests can retry");
  assert.equal(calls, 2);
  console.log("  failed dynamic lookups are shared, then retried on a later request");
}

async function main() {
  await checkSnapshotSubprocessTimeout();
  await checkSnapshotCacheRace();
  await checkInFlightDeduplication();
  await checkInFlightFailureRetry();
  await checkBoundedInFlight();
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
    for (const invalidId of ["0", "01", "-1", "9007199254740992", "1%2F2"]) {
      assert.equal((await fetch(base + `/api/match/${invalidId}`)).status, 404,
        `unsafe match ID ${invalidId} must not reach the match layer`);
    }
    console.log("  /api/match/:id movement and unknown IDs ok");

    const team = await fetch(base + "/api/team/4529");
    assert.equal(team.status, 200);
    const teamBody = await team.json();
    assert.equal(teamBody.team_id, 4529);
    assert.ok(Array.isArray(teamBody.results));
    for (const invalidId of ["0", "01", "-1", "9007199254740992", "1%2F2"]) {
      assert.equal((await fetch(base + `/api/team/${invalidId}`)).status, 404,
        `unsafe team ID ${invalidId} must not reach the team layer`);
    }
    console.log("  /api/team/:id identity and unknown IDs ok");

    const player = await fetch(base + "/api/player/9801");
    assert.equal(player.status, 200);
    const playerBody = await player.json();
    assert.equal(playerBody.player_id, 9801);
    assert.ok(playerBody.recorded_maps > 0 && playerBody.maps.length <= 20);
    assert.ok(Array.isArray(playerBody.agents) && Array.isArray(playerBody.teams));
    for (const invalidId of ["0", "01", "-1", "9007199254740992", "1%2F2"]) {
      assert.equal((await fetch(base + `/api/player/${invalidId}`)).status, 404,
        `unsafe player ID ${invalidId} must not reach the player layer`);
    }
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
    const logoEscape = path.join(__dirname, "../data/processed/logos/9999999998.svg");
    try {
      await fs.symlink("/etc/passwd", logoEscape);
      const escapedLogo = await fetch(base + "/logos/9999999998.svg");
      assert.equal(escapedLogo.status, 404, "logo serving must not follow symlinks outside the logo directory");
      assert.doesNotMatch(await escapedLogo.text(), /root:/, "outside files must not be served as logos");
    } finally {
      await fs.unlink(logoEscape).catch(() => {});
    }
    console.log("  /logos only serves contained numeric image files");

    const unknownApi = await fetch(base + "/api/nope");
    assert.equal(unknownApi.status, 404);
    assert.deepEqual((await unknownApi.json()).routes, [
      "/api/snapshot", "/api/fixtures", "/api/backtest", "/api/live", "/api/rankings",
      "/api/ledger", "/api/health", "/api/match/:id", "/api/team/:id", "/api/player/:id",
      "/api/champions/2766", "/api/paper-ledger", "/api/results", "/api/ops",
    ]);
    assert.equal((await fetch(base + "/assets/missing.js")).status, 404);
    assert.equal((await fetch(base + "/assets/..%2F..%2Fserver.js")).status, 404);
    const escapeLink = path.join(__dirname, "../web/dist/assets/autodev-escape.txt");
    try {
      await fs.symlink("/etc/passwd", escapeLink);
      const escaped = await fetch(base + "/assets/autodev-escape.txt");
      assert.equal(escaped.status, 404, "static assets must not follow symlinks outside web/dist");
      assert.doesNotMatch(await escaped.text(), /root:/, "outside files must not be served");
    } finally {
      await fs.unlink(escapeLink).catch(() => {});
    }
    assert.equal((await fetch(base + "/%E0%A4%A")).status, 400);
    assert.equal((await fetch(base + "/api/health")).status, 200,
      "malformed path must not take down the backend");

    const invalidTarget = await new Promise((resolve, reject) => {
      const socket = net.connect(server.address().port, "127.0.0.1", () => {
        socket.end("GET //[ HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
      });
      let response = "";
      socket.setEncoding("utf8");
      socket.on("data", chunk => { response += chunk; });
      socket.on("end", () => resolve(response));
      socket.on("error", reject);
    });
    assert.ok(invalidTarget.startsWith("HTTP/1.1 400 "),
      "invalid request target should return 400 without crashing the server");
    assert.equal((await fetch(base + "/api/health")).status, 200,
      "backend should survive an invalid request target");
    const readOnly = await fetch(base + "/api/snapshot", { method: "POST" });
    assert.equal(readOnly.status, 405);
    assert.equal(readOnly.headers.get("allow"), "GET, HEAD");
    const getHead = await fetch(base + "/api/health");
    assert.equal(getHead.headers.get("x-content-type-options"), "nosniff",
      "API responses should prevent MIME sniffing");
    const headApi = await fetch(base + "/api/health", { method: "HEAD" });
    assert.equal(headApi.status, getHead.status);
    assert.equal(headApi.headers.get("content-length"), getHead.headers.get("content-length"));
    assert.equal(await headApi.text(), "", "HEAD API response must not contain a body");
    const staticGet = await fetch(base + "/");
    assert.equal(staticGet.headers.get("x-content-type-options"), "nosniff",
      "static app responses should prevent MIME sniffing");
    const staticHead = await fetch(base + "/", { method: "HEAD" });
    assert.equal(staticHead.headers.get("content-length"), staticGet.headers.get("content-length"));
    assert.equal(await staticHead.text(), "", "HEAD static response must not contain a body");
    console.log("  unknown API/asset 404, traversal blocked, read-only 405 and HEAD semantics ok");
    console.log("all checks passed");
  } finally {
    server.close();
  }
}

main().catch(err => { console.error(err.message); process.exitCode = 1; });
