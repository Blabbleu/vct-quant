/**
 * Unit checks for the in-process API cache (api-cache.js) and its wiring in
 * server.js. No database needed except the last block, which boots the server.
 *
 *   node test/api-cache.test.js     (also run by `npm run check`)
 */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { createLimiter, createStamper, createSwrCache, createWarmer } = require("../api-cache.js");
const { server, API_CACHES, pythonJson, warmTeamIds } = require("../server.js");

const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate, label) {
  for (let i = 0; i < 200 && !predicate(); i += 1) await tick();
  assert.ok(predicate(), `timed out waiting for ${label}`);
}
function clock(start = 1000) {
  let t = start;
  const now = () => t;
  now.advance = ms => { t += ms; };
  return now;
}
function counter() {
  const calls = [];
  const compute = async key => { calls.push(key); return { key, n: calls.length }; };
  compute.calls = calls;
  return compute;
}

async function checkHitDoesNotRecompute() {
  const compute = counter();
  const now = clock();
  const cache = createSwrCache({ compute, readStamp: async () => "s1", ttlMs: 1000, now });
  const first = await cache.get("a");
  assert.equal(first.state, "miss");
  const second = await cache.get("a");
  assert.equal(second.state, "hit");
  assert.equal(second.value, first.value, "a hit must return the very same payload");
  assert.equal(compute.calls.length, 1, "a cache hit must not start a second computation");
  console.log("  cache hit returns the same body without a second computation");
}

async function checkPythonRunnerIsNotRespawned() {
  let spawns = 0;
  const run = (command, args, options, callback) => {
    spawns += 1;
    assert.deepEqual(args.slice(0, 2), ["-m", "vct_quant.results_list"]);
    setImmediate(() => callback(null, JSON.stringify({ rows: [spawns] }), ""));
  };
  const cache = createSwrCache({
    compute: () => pythonJson("results_list", [], "results list", run),
    readStamp: async () => "s1", ttlMs: 60000,
  });
  const bodies = [];
  for (let i = 0; i < 5; i += 1) bodies.push(JSON.stringify((await cache.get("all")).value));
  assert.equal(spawns, 1, "five reads of an unchanged input must spawn one python process");
  assert.equal(new Set(bodies).size, 1);
  await assert.rejects(pythonJson("x", [], "thing", (c, a, o, cb) => cb(new Error("boom"), "", "stderr text")), /stderr text/);
  await assert.rejects(pythonJson("x", [], "thing", (c, a, o, cb) => cb(null, "not json", "")), /bad JSON from thing/);
  console.log("  python runner spawns once for repeated reads; errors and bad JSON reject");
}

async function checkPythonAbortRetriedOnce() {
  const abort = "terminate called without an active exception";
  let calls = 0;
  const flaky = (c, a, o, cb) => {
    calls += 1;
    if (calls === 1) return setImmediate(() => cb(Object.assign(new Error("Command failed"), { code: null, signal: "SIGABRT" }), "", abort));
    setImmediate(() => cb(null, JSON.stringify({ ok: true }), ""));
  };
  assert.deepEqual(await pythonJson("champions_status", [], "Champions status", flaky), { ok: true });
  assert.equal(calls, 2, "an abort is retried once and the retry's body is returned");

  calls = 0;
  const alwaysAborts = (c, a, o, cb) => { calls += 1; setImmediate(() => cb(new Error("Command failed"), "", abort)); };
  await assert.rejects(pythonJson("champions_status", [], "Champions status", alwaysAborts), /terminate called/);
  assert.equal(calls, 2, "a persistent abort is attempted exactly twice, then rejects");

  calls = 0;
  const plainFailure = (c, a, o, cb) => { calls += 1; setImmediate(() => cb(new Error("Command failed"), "", "ValueError: bad id")); };
  await assert.rejects(pythonJson("team_profile", ["1"], "team profile", plainFailure), /ValueError/);
  assert.equal(calls, 1, "ordinary python errors are not retried");

  calls = 0;
  const badJson = (c, a, o, cb) => { calls += 1; setImmediate(() => cb(null, "nope", "")); };
  await assert.rejects(pythonJson("x", [], "thing", badJson), /bad JSON/);
  assert.equal(calls, 1, "bad JSON is not retried");
  console.log("  python aborts (terminate/SIGABRT) are retried once; other failures are not");
}

async function checkInvalidationOnInputChange() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "vct-cache-"));
  try {
    const input = path.join(dir, "prediction_log.parquet");
    const other = path.join(dir, "missing.json");
    await fs.writeFile(input, "v1");
    const stamp = createStamper([input, other]);
    const before = await stamp();
    assert.equal(await stamp(), before, "an untouched input keeps its stamp");
    const compute = counter();
    const now = clock();
    const cache = createSwrCache({ compute, readStamp: stamp, ttlMs: 10 * 60 * 1000, now });
    await cache.get("a");
    await fs.utimes(input, new Date(Date.now() + 5000), new Date(Date.now() + 5000));
    const afterTouch = await stamp();
    assert.notEqual(afterTouch, before, "a changed mtime must change the stamp");
    const stale = await cache.get("a");
    assert.equal(stale.state, "stale", "changed inputs serve the old body immediately");
    assert.equal(stale.value.n, 1);
    await until(() => compute.calls.length === 2, "background refresh");
    await until(() => cache.peek("a").n === 2, "refreshed value stored");
    assert.equal((await cache.get("a")).state, "hit", "after the refresh the new body is a hit");
    const forced = await cache.get("a", { waitForFresh: true });
    assert.equal(forced.state, "hit");
    await fs.writeFile(other, "appears");
    assert.notEqual(await stamp(), afterTouch, "a file appearing must invalidate");
    await fs.writeFile(input, "v2-longer");
    await fs.unlink(other);
    assert.notEqual(await stamp(), afterTouch, "a changed size must invalidate");
    const waited = await cache.get("a", { waitForFresh: true });
    assert.equal(waited.state, "miss", "waitForFresh blocks on a recompute when stale");
    assert.equal(waited.value.n, 3);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
  console.log("  input mtime/size change invalidates (stale served, background refresh swaps it in)");
}

async function checkTtlCeiling() {
  const compute = counter();
  const now = clock();
  const cache = createSwrCache({ compute, readStamp: async () => "same", ttlMs: 1000, maxStaleMs: 5000, now });
  await cache.get("a");
  now.advance(1500);
  assert.equal((await cache.get("a")).state, "stale", "past the TTL with unchanged inputs still refreshes");
  await until(() => cache.peek("a").n === 2, "TTL refresh stored");
  now.advance(9000);
  const tooOld = await cache.get("a");
  assert.equal(tooOld.state, "miss", "an entry older than maxStale is never served");
  assert.equal(compute.calls.length, 3);
  console.log("  TTL ceiling refreshes unchanged inputs; over-stale entries are not served");
}

async function checkCoalescing() {
  let release;
  let calls = 0;
  const cache = createSwrCache({
    compute: () => { calls += 1; return new Promise(resolve => { release = () => resolve({ calls }); }); },
    readStamp: async () => "s", ttlMs: 1000,
  });
  const requests = Array.from({ length: 8 }, () => cache.get("team:1"));
  await until(() => release, "compute started");
  release();
  const results = await Promise.all(requests);
  assert.equal(calls, 1, "eight concurrent identical requests must share one computation");
  assert.ok(results.every(r => r.value === results[0].value));
  console.log("  concurrent identical requests coalesce into one computation");
}

async function checkStaleRefreshCoalescesAndBacksOff() {
  let fail = false;
  let calls = 0;
  const errors = [];
  const now = clock();
  const stampBox = { value: "a" };
  const cache = createSwrCache({
    compute: async () => { calls += 1; if (fail) throw new Error("db locked"); return { v: calls }; },
    readStamp: async () => stampBox.value, ttlMs: 1000, retryMs: 5000, now,
    onError: (key, error) => errors.push(error.message),
  });
  await cache.get("k");
  stampBox.value = "b";
  fail = true;
  const [one, two, three] = await Promise.all([cache.get("k"), cache.get("k"), cache.get("k")]);
  assert.deepEqual([one.state, two.state, three.state], ["stale", "stale", "stale"]);
  await until(() => errors.length === 1, "failed refresh reported");
  assert.equal(calls, 2, "three stale readers start one refresh");
  assert.equal((await cache.get("k")).value.v, 1, "a failed refresh keeps serving the last good body");
  await tick();
  assert.equal(calls, 2, "no retry storm inside the back-off window");
  now.advance(6000);
  fail = false;
  await cache.get("k");
  await until(() => calls === 3, "retry after back-off");
  await until(() => cache.peek("k").v === 3, "recovered value stored");
  console.log("  failed refresh keeps the last good body, backs off, then recovers");

  const failing = createSwrCache({ compute: async () => { throw new Error("nope"); }, readStamp: async () => "s", ttlMs: 1000 });
  await assert.rejects(failing.get("x"), /nope/, "a failed miss must reject");
  assert.equal(failing.has("x"), false, "a failed miss must not be cached");
}

async function checkLruBound() {
  const compute = counter();
  const cache = createSwrCache({ compute, readStamp: async () => "s", ttlMs: 1000, max: 3 });
  for (const key of ["a", "b", "c"]) await cache.get(key);
  await cache.get("a");              // a is now most recently used
  await cache.get("d");              // evicts b, the least recently used
  assert.deepEqual(cache.keys().sort(), ["a", "c", "d"]);
  assert.equal(cache.size, 3);
  for (let i = 0; i < 50; i += 1) await cache.get(`k${i}`);
  assert.equal(cache.size, 3, "per-id caches must stay bounded");
  const before = compute.calls.length;
  await cache.get("k49");
  assert.equal(compute.calls.length, before, "the newest entries survive eviction");
  assert.throws(() => createSwrCache({ compute, readStamp: async () => "s", ttlMs: 1000, max: 0 }), RangeError);
  console.log("  LRU keeps at most max entries and evicts the least recently used");
}

async function checkLimiter() {
  const limit = createLimiter(2);
  let active = 0;
  let peak = 0;
  const releases = [];
  const jobs = Array.from({ length: 5 }, (_, i) => limit(() => {
    active += 1;
    peak = Math.max(peak, active);
    return new Promise(resolve => releases.push(() => { active -= 1; resolve(i); }));
  }));
  await until(() => releases.length === 2, "two slots filled");
  assert.deepEqual(limit.stats(), { active: 2, queued: 3 });
  while (releases.length) {
    releases.shift()();
    await tick();
    await tick();
  }
  await until(() => releases.length > 0 || active === 0, "queue drained");
  while (releases.length) { releases.shift()(); await tick(); await tick(); }
  assert.deepEqual(await Promise.all(jobs), [0, 1, 2, 3, 4]);
  assert.equal(peak, 2, "never more than the limit of processes at once");
  assert.throws(() => createLimiter(0), RangeError);
  console.log("  process limiter caps concurrency and preserves order");
}

async function checkWarmer() {
  let value = "v1";
  let warms = 0;
  const logs = [];
  const warmer = createWarmer({
    stamp: async () => value, warm: async () => { warms += 1; }, intervalMs: 1e9, stableTicks: 2,
    log: message => logs.push(message),
  });
  await warmer.start();
  warmer.stop();
  assert.equal(warms, 1, "warm at start");
  await warmer.tick();
  assert.equal(warms, 1, "unchanged inputs do not re-warm");
  value = "v2";
  await warmer.tick();
  assert.equal(warms, 1, "first sight of a change waits (a refresh writes several files)");
  value = "v3";
  await warmer.tick();
  await warmer.tick();
  assert.equal(warms, 2, "re-warm once the inputs stay put for two polls");
  await warmer.tick();
  assert.equal(warms, 2);
  const broken = createWarmer({ stamp: async () => "x", warm: async () => { throw new Error("python missing"); }, log: message => logs.push(message) });
  await broken.start();
  broken.stop();
  assert.ok(logs.some(line => /failed: python missing/.test(line)), "warm failures are logged, never thrown");
  console.log("  warmer runs at start and after changed inputs settle; failures never throw");
}

function checkWarmTeamSelection() {
  const data = {
    fixtures: [{ logo_a: "/logos/1034.png", logo_b: "/logos/14.png" }, { logo_a: null, logo_b: "/logos/14.png" }],
    rankings: Array.from({ length: 30 }, (_, i) => ({ logo: `/logos/${100 + i}.png` })),
  };
  const ids = warmTeamIds(data, { groups: { A: { entrants: { 120: "x", 14: "y" } } } });
  assert.deepEqual(ids.slice(0, 2), [1034, 14], "fixture teams come first");
  assert.equal(ids.filter(id => id >= 100 && id < 130).length, 21, "top 20 rankings plus Champions entrant 120");
  assert.equal(new Set(ids).size, ids.length, "ids are unique");
  assert.deepEqual(warmTeamIds(null, null), []);
  console.log("  warm-up team selection: fixtures, top 20 rankings and Champions entrants, unique and bounded");
}

async function checkHttpCaching() {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    for (const route of ["/api/results", "/api/paper-ledger", "/api/champions/2766", "/api/team/4529", "/api/snapshot", "/api/rankings"]) {
      const first = await fetch(base + route, { headers: { "accept-encoding": "identity" } });
      assert.equal(first.status, 200, `${route} answered ${first.status}`);
      assert.equal(first.headers.get("cache-control"), "no-cache", `${route} must revalidate`);
      const etag = first.headers.get("etag");
      assert.ok(etag, `${route} must carry an ETag`);
      const body = await first.text();
      const second = await fetch(base + route, { headers: { "accept-encoding": "identity" } });
      assert.equal(await second.text(), body, `${route} must serve the same body again`);
      assert.equal(second.headers.get("etag"), etag);
      if (route !== "/api/snapshot" && route !== "/api/rankings") {
        assert.equal(second.headers.get("x-cache"), "hit", `${route} second read must come from memory`);
      }
      const conditional = await fetch(base + route, { headers: { "accept-encoding": "identity", "if-none-match": etag } });
      assert.equal(conditional.status, 304, `${route} must answer 304 for a matching ETag`);
      assert.equal(await conditional.text(), "");
      const weak = await fetch(base + route, { headers: { "accept-encoding": "identity", "if-none-match": `W/${etag}` } });
      assert.equal(weak.status, 304);
      const mismatch = await fetch(base + route, { headers: { "accept-encoding": "identity", "if-none-match": "\"other\"" } });
      assert.equal(mismatch.status, 200);
    }
    const health = await fetch(base + "/api/health");
    assert.equal(health.headers.get("cache-control"), "no-store", "health stays uncacheable");
    const missing = await fetch(base + "/api/team/999999999");
    assert.equal(missing.status, 404);
    assert.equal(missing.headers.get("etag"), null, "404 bodies carry no validator");
    console.log("  HTTP: cached python endpoints answer hit, ETag, 304 and weak-ETag 304");
    assert.ok(API_CACHES.team.size <= 200);
  } finally {
    server.close();
  }
}

async function main() {
  await checkHitDoesNotRecompute();
  await checkPythonRunnerIsNotRespawned();
  await checkPythonAbortRetriedOnce();
  await checkInvalidationOnInputChange();
  await checkTtlCeiling();
  await checkCoalescing();
  await checkStaleRefreshCoalescesAndBacksOff();
  await checkLruBound();
  await checkLimiter();
  await checkWarmer();
  checkWarmTeamSelection();
  if (process.env.VCT_CACHE_TEST_HTTP !== "0") await checkHttpCaching();
  console.log("api cache checks passed");
}

main().catch(err => { console.error(err.stack || err.message); process.exitCode = 1; });
