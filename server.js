/**
 * Backend for the VCT quant desk.
 *
 *   node server.js            # http://127.0.0.1:8000
 *   PORT=9000 node server.js
 *
 * The model lives in Python, so this server shells out to
 * `python -m vct_quant.dashboard`, which prints the payload as JSON, and caches
 * the result against the DuckDB file's mtime: page reloads are free until the
 * next `vct update` rewrites the database. Read-only by design -- DuckDB takes
 * one writer at a time, and ingestion stays a command-line job.
 *
 * No dependencies: node's own http, fs and child_process.
 */
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { execFile } = require("node:child_process");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const { createLimiter, createStamper, createSwrCache, createWarmer } = require("./api-cache");

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 8000);
const HOST = process.env.HOST || "127.0.0.1";
const DB = path.join(ROOT, "data", "vct.duckdb");
const SEARCH_INDEX = path.join(ROOT, "data", "processed", "search_index.json");
const PYTHON = process.env.PYTHON ||
  path.join(ROOT, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

function computeSnapshot(run = execFile) {
  return new Promise((resolve, reject) => {
    run(PYTHON, ["-m", "vct_quant.dashboard"], { cwd: ROOT, maxBuffer: 64 << 20, timeout: 120000 },
      (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from the model layer: ${parseError.message}`));
        }
      });
  });
}

function createSnapshotter(readStamp, compute) {
  let cached = { stamp: null, payload: null };
  let pending = null;
  return async function getSnapshot() {
    while (true) {
      const stamp = await readStamp();
      if (cached.stamp === stamp && cached.payload) return cached.payload;
      if (pending && pending.stamp !== stamp) {
        await pending.promise.catch(() => {});
        continue;
      }
      if (!pending) {
        const entry = { stamp, promise: Promise.resolve().then(compute) };
        pending = entry;
        entry.promise.finally(() => {
          if (pending === entry) pending = null;
        }).catch(() => {});
      }
      const entry = pending;
      const payload = await entry.promise;
      if (pending === entry) pending = null;
      if (await readStamp() !== stamp) continue;
      cached = { stamp, payload };
      return payload;
    }
  };
}

const snapshot = createSnapshotter(
  () => fs.stat(DB).then(s => String(s.mtimeMs), () => "no-db"),
  computeSnapshot,
);

function createInFlight(compute) {
  const pending = new Map();
  return key => {
    if (!pending.has(key)) {
      let promise;
      try {
        promise = Promise.resolve(compute(key));
      } catch (err) {
        promise = Promise.reject(err);
      }
      pending.set(key, promise);
      promise.finally(() => {
        if (pending.get(key) === promise) pending.delete(key);
      }).catch(() => {});
    }
    return pending.get(key);
  };
}

function createBoundedInFlight(compute, concurrency = 4, maxQueued = 32) {
  if (!Number.isSafeInteger(concurrency) || concurrency < 1 ||
      !Number.isSafeInteger(maxQueued) || maxQueued < 0) {
    throw new RangeError("concurrency must be positive and maxQueued non-negative");
  }
  const pending = new Map();
  const queue = [];
  let active = 0;

  function start(entry) {
    active += 1;
    Promise.resolve().then(() => compute(entry.key)).then(entry.resolve, entry.reject)
      .finally(() => {
        if (pending.get(entry.key) === entry.promise) pending.delete(entry.key);
        active -= 1;
        drain();
      });
  }

  function drain() {
    while (active < concurrency && queue.length) {
      const entry = queue.shift();
      if (pending.get(entry.key) === entry.promise) start(entry);
    }
  }

  return key => {
    if (pending.has(key)) return pending.get(key);
    if (active >= concurrency && queue.length >= maxQueued) {
      const error = new Error("dynamic lookup capacity exceeded");
      error.code = "OVERLOADED";
      return Promise.reject(error);
    }
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    const entry = { key, promise, resolve, reject };
    pending.set(key, promise);
    if (active < concurrency) start(entry);
    else queue.push(entry);
    return promise;
  };
}

// Every python-backed endpoint goes through here: one place for the timeout,
// the JSON parse, and a global cap on simultaneous interpreters (pandas+duckdb
// is ~200 MB each; the box has 3 cores). `run` is injectable for tests.
const PYTHON_PROCESSES = Number(process.env.VCT_PYTHON_PROCESSES || 3);
const limitPython = createLimiter(PYTHON_PROCESSES);

function pythonJson(moduleName, args, label, run = execFile) {
  return limitPython(() => new Promise((resolve, reject) => {
    run(PYTHON, ["-m", `vct_quant.${moduleName}`, ...args],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(String(stderr || "").trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from ${label}: ${parseError.message}`));
        }
      });
  }));
}

const computeMatchInFlight = createBoundedInFlight(id => pythonJson("match_center", [id], "match center"), 2, 16);
const computeTeamInFlight = createBoundedInFlight(id => pythonJson("team_profile", [id], "team profile"), 2, 16);
const computePlayerInFlight = createBoundedInFlight(id => pythonJson("player_profile", [id], "player profile"), 2, 16);

// Inputs the python modules read. The cache is keyed on these files (mtime and
// size), so `vct update` / the matchday refresh invalidates it and nothing else
// does; the TTLs below are only a ceiling for the few outputs that also depend
// on the clock (upcoming vs played, ages). The DuckDB write-ahead log is part
// of the stamp because uncheckpointed writes change results without touching
// the main file.
const DATA_INPUTS = [
  DB, `${DB}.wal`,
  path.join(ROOT, "data", "processed", "prediction_log.parquet"),
  path.join(ROOT, "data", "processed", "upcoming_tier1.parquet"),
  path.join(ROOT, "data", "processed", "team_logos.json"),
  path.join(ROOT, "data", "processed", "player_photos.json"),
  path.join(ROOT, "config", "brackets", "champions_2026.json"),
];
const OPS_INPUTS = [
  ...DATA_INPUTS,
  process.env.VCT_MATCHDAY_LOG || path.join(ROOT, "data", "interim", "matchday.log"),
  path.join(ROOT, "data", "raw", "vlrgg"),
  path.join(ROOT, "data", "raw", "polymarket"),
];
const readDataStamp = createStamper(DATA_INPUTS, { memoMs: 500 });
const readOpsStamp = createStamper(OPS_INPUTS, { memoMs: 500 });

const MINUTE = 60 * 1000;
function logCacheError(name) {
  return (key, error) => console.error(`[cache:${name}] refresh ${key} failed: ${error.message}`);
}
function makeCache(name, compute, ttlMs, { max = 200, maxStaleMs = 30 * MINUTE, readStamp = readDataStamp } = {}) {
  return createSwrCache({ compute, readStamp, ttlMs, maxStaleMs, max, onError: logCacheError(name) });
}

const API_CACHES = {
  match: makeCache("match", computeMatchInFlight, 10 * MINUTE),
  team: makeCache("team", computeTeamInFlight, 10 * MINUTE),
  player: makeCache("player", computePlayerInFlight, 10 * MINUTE),
  champions: makeCache("champions", () => pythonJson("champions_status", [], "Champions status"), 5 * MINUTE, { max: 1 }),
  paperLedger: makeCache("paper-ledger", () => pythonJson("paper_ledger", [], "paper ledger"), 5 * MINUTE, { max: 1 }),
  results: makeCache("results", () => pythonJson("results_list", [], "results list"), 5 * MINUTE, { max: 1 }),
  // Ops is about freshness (matchday log age, newest raw snapshot): short TTL
  // and a tight staleness cap, but still cached so the page never waits.
  ops: makeCache("ops", () => pythonJson("ops_status", [], "ops status"), 30 * 1000,
    { max: 1, maxStaleMs: 2 * MINUTE, readStamp: readOpsStamp }),
};

let cachedSearchIndex = { stamp: null, payload: null };
async function readSearchIndex() {
  const stat = await fs.stat(SEARCH_INDEX);
  const stamp = `${stat.mtimeMs}:${stat.size}`;
  if (cachedSearchIndex.stamp === stamp && cachedSearchIndex.payload) return cachedSearchIndex.payload;
  const payload = JSON.parse(await fs.readFile(SEARCH_INDEX, "utf8"));
  if (!payload || !Array.isArray(payload.teams) || !Array.isArray(payload.players) ||
      !Array.isArray(payload.events)) throw new Error("invalid search index shape");
  cachedSearchIndex = { stamp, payload };
  return payload;
}

function foldSearchText(value) {
  return String(value ?? "").normalize("NFKD").replace(/\p{M}/gu, "")
    .replace(/ı/g, "i").toLocaleLowerCase();
}

function searchIndex(index, query, limit = 20) {
  const rawQuery = String(query).trim();
  const needle = foldSearchText(rawQuery).trim();
  if (!rawQuery) return index;
  if (!needle) return { query: rawQuery, teams: [], players: [], events: [] };
  const fields = {
    teams: ["id", "name", "tag"],
    players: ["id", "handle", "real_name", "team_name"],
    events: ["id", "name"],
  };
  const result = { query: String(query).trim() };
  for (const [kind, keys] of Object.entries(fields)) {
    const matches = index[kind].map((row, position) => {
      const values = keys.map(key => foldSearchText(row[key]));
      if (!values.some(value => value.includes(needle))) return null;
      const rank = values.some(value => value === needle) ? 0
        : values.some(value => value.startsWith(needle)) ? 1 : 2;
      return { row, position, rank };
    }).filter(Boolean)
      .sort((a, b) => a.rank - b.rank || a.position - b.position)
      .slice(0, limit).map(item => item.row);
    result[kind] = matches;
  }
  return result;
}

function parseSearchRequest(url) {
  if (url.searchParams.getAll("q").length > 1 || url.searchParams.getAll("limit").length > 1) {
    return { error: "q and limit may each be supplied at most once" };
  }
  if (!url.searchParams.has("q")) {
    if (url.searchParams.has("limit")) return { error: "q is required when limit is supplied" };
    return { query: null };
  }
  const query = url.searchParams.get("q").trim();
  if (!query || query.length > 100) return { error: "q must contain 1 to 100 characters" };
  const rawLimit = url.searchParams.get("limit");
  if (rawLimit === null) return { query, limit: 20 };
  if (!/^(?:[1-9]|[1-4][0-9]|50)$/.test(rawLimit)) return { error: "limit must be an integer from 1 to 50" };
  return { query, limit: Number(rawLimit) };
}

const ROUTES = {
  "/api/snapshot": data => data,
  "/api/fixtures": data => data.fixtures,
  "/api/backtest": data => data.backtest,
  "/api/live": data => data.live,
  "/api/rankings": data => ({ season: data.season, rankings: data.rankings }),
  "/api/ledger": data => data.ledger,
  "/api/health": data => ({ ok: true, generated_at: data.generated_at, coverage: data.coverage }),
};

const API_ROUTES = [
  ...Object.keys(ROUTES),
  "/api/match/:id", "/api/team/:id", "/api/player/:id", "/api/champions/2766",
  "/api/paper-ledger", "/api/results", "/api/ops", "/api/search",
];

function modelFailurePayload() {
  return {
    error: "the model layer failed",
    hint: "run `vct init-db` and `vct update` first, or set PYTHON to your interpreter",
  };
}

function acceptsGzip(header = "") {
  const encodings = new Map();
  for (const item of header.split(",")) {
    const [rawName, ...params] = item.trim().split(";");
    const name = rawName.toLowerCase();
    const q = params.map(part => part.trim()).find(part => /^q=/i.test(part));
    const quality = q ? Number(q.slice(2)) : 1;
    if (name && Number.isFinite(quality) && quality >= 0 && quality <= 1) encodings.set(name, quality);
  }
  return (encodings.has("gzip") ? encodings.get("gzip") : encodings.get("*") ?? 0) > 0;
}

function send(res, status, body, type = "application/json; charset=utf-8", options = {}) {
  const headers = {
    "content-type": type,
    "cache-control": options.cacheControl || "no-store",
    "content-length": Buffer.byteLength(body),
    "x-content-type-options": "nosniff",
  };
  if (type.startsWith("application/json")) headers.vary = "Accept-Encoding";
  if (type.startsWith("application/json") && Buffer.byteLength(body) >= 1024 && acceptsGzip(res.req.headers["accept-encoding"])) {
    body = zlib.gzipSync(body);
    headers["content-encoding"] = "gzip";
    headers["content-length"] = body.length;
  }
  if (options.etag) {
    const etag = `"${crypto.createHash("sha256").update(body).digest("base64url")}"`;
    headers.etag = etag;
    const candidates = (res.req.headers["if-none-match"] || "").split(",").map(value => value.trim());
    const matches = candidates.includes("*") || candidates.some(value => (value.startsWith("W/") ? value.slice(2) : value) === etag);
    if (matches && status === 200 && ["GET", "HEAD"].includes(res.req.method)) {
      delete headers["content-type"];
      delete headers["content-length"];
      delete headers["content-encoding"];
      res.writeHead(304, headers);
      return res.end();
    }
  }
  res.writeHead(status, headers);
  res.end(body);
}

// Built multipage app (web/, `npm run build` -> web/dist). Hashed assets are
// served from dist/assets; every other non-API path gets index.html so the
// client router can render /matches, /match/:id, /rankings, ... on reload.
const DIST = path.join(ROOT, "web", "dist");
const TYPES = {
  ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
};

async function serveApp(res, pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return send(res, 400, JSON.stringify({ error: "malformed path" }));
  }
  const rel = path.normalize(decoded).replace(/^([/\\])+/, "");
  const file = path.join(DIST, rel);
  const ext = path.extname(rel);
  if (rel && ext && ext !== ".html" && file.startsWith(DIST + path.sep)) {
    try {
      const root = await fs.realpath(DIST);
      const resolved = await fs.realpath(file);
      if (!resolved.startsWith(root + path.sep)) {
        return send(res, 404, JSON.stringify({ error: "not found" }));
      }
      const body = await fs.readFile(resolved);
      res.writeHead(200, {
        "content-type": TYPES[ext] || "application/octet-stream",
        "content-length": body.length,
        "cache-control": rel.startsWith("assets/") ? "public, max-age=31536000, immutable" : "no-cache",
        "x-content-type-options": "nosniff",
      });
      return res.end(body);
    } catch {
      return send(res, 404, JSON.stringify({ error: "not found" }));
    }
  }
  try {
    const page = await fs.readFile(path.join(DIST, "index.html"), "utf8");
    return send(res, 200, page, "text/html; charset=utf-8");
  } catch {
    // Not built yet: fall back to the legacy single-file desk.
    const page = await fs.readFile(path.join(ROOT, "frontend", "index.html"), "utf8");
    return send(res, 200, page, "text/html; charset=utf-8");
  }
}

// ---- warm-up ---------------------------------------------------------------
// Recompute the expensive entries in the background so the first visitor after a
// restart or a matchday refresh is served from memory. Low concurrency (leaves
// slots for real requests), never awaited by a request, and never throws.
const WARM_CONCURRENCY = 2;
const WARM_TEAM_LIMIT = 40;
const TEAM_FROM_LOGO = /^\/logos\/([1-9][0-9]*)\./;

function warmTeamIds(data, championsPayload) {
  const ids = new Set();
  const add = value => {
    const id = Number(value);
    if (Number.isSafeInteger(id) && id > 0) ids.add(id);
  };
  const fromLogo = logo => TEAM_FROM_LOGO.exec(String(logo ?? ""))?.[1];
  for (const fixture of data?.fixtures ?? []) { add(fromLogo(fixture.logo_a)); add(fromLogo(fixture.logo_b)); }
  for (const row of (data?.rankings ?? []).slice(0, 20)) add(fromLogo(row.logo));
  for (const group of Object.values(championsPayload?.groups ?? {})) {
    for (const id of Object.keys(group.entrants ?? {})) add(id);
  }
  return [...ids].slice(0, WARM_TEAM_LIMIT);
}

async function runPool(items, worker, concurrency = WARM_CONCURRENCY) {
  const queue = [...items];
  await Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
    while (queue.length) {
      const item = queue.shift();
      try { await worker(item); } catch { /* logged by the cache; keep warming the rest */ }
    }
  }));
}

async function warmCaches() {
  const [data, championsEntry] = await Promise.all([
    snapshot().catch(() => null),
    API_CACHES.champions.refresh("all").catch(() => null),
    API_CACHES.results.refresh("all").catch(() => null),
    API_CACHES.paperLedger.refresh("all").catch(() => null),
  ]);
  await readSearchIndex().catch(() => {});
  const teamIds = warmTeamIds(data, championsEntry?.value);
  await runPool(teamIds, id => API_CACHES.team.refresh(String(id)));
  const matchIds = (data?.fixtures ?? []).slice(0, 12).map(f => String(f.match_id));
  await runPool(matchIds, id => API_CACHES.match.refresh(id));
  await API_CACHES.ops.refresh("all").catch(() => {});
}

const warmer = createWarmer({
  stamp: readDataStamp,
  warm: warmCaches,
  intervalMs: Number(process.env.VCT_WARM_INTERVAL_MS || 10000),
  log: message => console.log(`[cache] ${message}`),
});

const REVALIDATE = { cacheControl: "no-cache", etag: true };

// Serve one cached python-backed payload: ETag + `no-cache` so the browser
// revalidates every time and gets a 304 until the data changes. `x-cache`
// reports hit | stale | miss for debugging and the tests.
async function sendCached(res, url, cache, key, { missing, failure, busy, waitForFresh = false }) {
  try {
    const { value, state } = await cache.get(key, { waitForFresh });
    res.setHeader("x-cache", state);
    return value === null
      ? send(res, 404, JSON.stringify({ error: missing }))
      : send(res, 200, JSON.stringify(value), undefined, REVALIDATE);
  } catch (err) {
    if (err.code === "OVERLOADED") {
      res.setHeader("retry-after", "1");
      return send(res, 503, JSON.stringify({ error: busy }));
    }
    console.error(`[500] ${url.pathname}: ${err.message}`);
    return send(res, 500, JSON.stringify({ error: failure }));
  }
}

const server = http.createServer(async (req, res) => {
  let url;
  try {
    url = new URL(req.url, `http://${req.headers.host}`);
  } catch {
    return send(res, 400, JSON.stringify({ error: "malformed path" }));
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.setHeader("allow", "GET, HEAD");
    return send(res, 405, JSON.stringify({ error: "read-only API: GET only" }));
  }
  const route = ROUTES[url.pathname];
  if (route) {
    try {
      const body = JSON.stringify(route(await snapshot()));
      return url.pathname === "/api/health" ? send(res, 200, body) : send(res, 200, body, undefined, REVALIDATE);
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify(modelFailurePayload()));
    }
  }
  const dynamic = [
    [/^\/api\/match\/([1-9][0-9]*)$/, API_CACHES.match, "match", "match not found in prediction log", "the match layer failed"],
    [/^\/api\/team\/([1-9][0-9]*)$/, API_CACHES.team, "team", "team not found in Tier-1 history or cached fixtures", "the team layer failed"],
    [/^\/api\/player\/([1-9][0-9]*)$/, API_CACHES.player, "player", "player ID not found", "the player layer failed"],
  ];
  for (const [pattern, cache, label, missing, failure] of dynamic) {
    const hit = pattern.exec(url.pathname);
    if (!hit || !Number.isSafeInteger(Number(hit[1]))) continue;
    return sendCached(res, url, cache, hit[1], { missing, failure, busy: `${label} lookups are busy; retry shortly` });
  }
  const singletons = {
    "/api/champions/2766": [API_CACHES.champions, "the Champions layer failed"],
    "/api/paper-ledger": [API_CACHES.paperLedger, "the paper ledger failed"],
    "/api/results": [API_CACHES.results, "the results list failed"],
    "/api/ops": [API_CACHES.ops, "the ops status failed", true],
  };
  if (Object.hasOwn(singletons, url.pathname)) {
    // Ops never serves a body older than its TTL: freshness is its whole point and
    // the lookup is cheap (~0.5 s), so a stale entry makes the request wait for a new one.
    const [cache, failure, waitForFresh] = singletons[url.pathname];
    return sendCached(res, url, cache, "all", { failure, waitForFresh: waitForFresh === true });
  }
  if (url.pathname === "/api/search") {
    try {
      const search = parseSearchRequest(url);
      if (search.error) return send(res, 400, JSON.stringify({ error: search.error }));
      const index = await readSearchIndex();
      return send(res, 200, JSON.stringify(search.query === null
        ? index : searchIndex(index, search.query, search.limit)), undefined,
      { cacheControl: "no-cache", etag: true });
    } catch (err) {
      console.error(`[503] ${url.pathname}: ${err.message}`);
      return send(res, 503, JSON.stringify({ error: "search index is unavailable; run the matchday refresh" }));
    }
  }
  if (url.pathname.startsWith("/api/")) {
    return send(res, 404, JSON.stringify({ error: "not found", routes: API_ROUTES }));
  }
  const logo = /^\/logos\/([1-9][0-9]{0,9})\.(png|jpg|webp|svg)$/.exec(url.pathname);
  const playerPhoto = new RegExp("^/players/([1-9][0-9]{0,9})[.](png|jpg|webp)$").exec(url.pathname);
  if (playerPhoto) {
    try {
      const projectRoot = await fs.realpath(ROOT);
      const photoRoot = await fs.realpath(path.join(ROOT, "data", "processed", "players"));
      if (!photoRoot.startsWith(projectRoot + path.sep)) return send(res, 404, JSON.stringify({ error: "no player photo" }));
      const file = await fs.realpath(path.join(photoRoot, `${playerPhoto[1]}.${playerPhoto[2]}`));
      if (!file.startsWith(photoRoot + path.sep)) return send(res, 404, JSON.stringify({ error: "no player photo" }));
      const body = await fs.readFile(file);
      res.writeHead(200, { "content-type": TYPES["." + playerPhoto[2]], "content-length": body.length,
        "cache-control": "public, max-age=86400", "x-content-type-options": "nosniff" });
      return res.end(body);
    } catch {
      return send(res, 404, JSON.stringify({ error: "no player photo" }));
    }
  }
  if (logo) {
    try {
      const projectRoot = await fs.realpath(ROOT);
      const logoRoot = await fs.realpath(path.join(ROOT, "data", "processed", "logos"));
      if (!logoRoot.startsWith(projectRoot + path.sep)) {
        return send(res, 404, JSON.stringify({ error: "no logo" }));
      }
      const file = await fs.realpath(path.join(logoRoot, `${logo[1]}.${logo[2]}`));
      if (!file.startsWith(logoRoot + path.sep)) {
        return send(res, 404, JSON.stringify({ error: "no logo" }));
      }
      const body = await fs.readFile(file);
      res.writeHead(200, {
        "content-type": TYPES["." + logo[2]] || "application/octet-stream",
        "content-length": body.length,
        "cache-control": "public, max-age=86400",
        "x-content-type-options": "nosniff",
        ...(logo[2] === "svg" ? { "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'" } : {}),
      });
      return res.end(body);
    } catch {
      return send(res, 404, JSON.stringify({ error: "no logo" }));
    }
  }
  const agentIcon = /^\/agents\/([a-z]{2,16})\.png$/.exec(url.pathname);
  if (agentIcon) {
    try {
      const projectRoot = await fs.realpath(ROOT);
      const agentRoot = await fs.realpath(path.join(ROOT, "data", "processed", "agents"));
      if (!agentRoot.startsWith(projectRoot + path.sep)) {
        return send(res, 404, JSON.stringify({ error: "no agent icon" }));
      }
      const file = await fs.realpath(path.join(agentRoot, `${agentIcon[1]}.png`));
      if (!file.startsWith(agentRoot + path.sep)) {
        return send(res, 404, JSON.stringify({ error: "no agent icon" }));
      }
      const body = await fs.readFile(file);
      res.writeHead(200, {
        "content-type": "image/png",
        "content-length": body.length,
        "cache-control": "public, max-age=86400",
        "x-content-type-options": "nosniff",
      });
      return res.end(body);
    } catch {
      return send(res, 404, JSON.stringify({ error: "no agent icon" }));
    }
  }
  // The legacy single-page desk stays reachable while the web app grows.
  if (url.pathname === "/legacy" || url.pathname.startsWith("/legacy/")) {
    const page = await fs.readFile(path.join(ROOT, "frontend", "index.html"), "utf8");
    return send(res, 200, page, "text/html; charset=utf-8");
  }
  return serveApp(res, url.pathname);
});

if (require.main === module) {
  server.listen(PORT, HOST, () => {
    console.log(`desk backend on http://${HOST}:${PORT}`);
    console.log(`  routes: ${Object.keys(ROUTES).join(" ")}`);
    if (process.env.VCT_WARM !== "0") warmer.start().catch(() => {});
  });
}

module.exports = { server, snapshot, API_CACHES, warmer, warmTeamIds, pythonJson, DATA_INPUTS, ROUTES, computeSnapshot, createSnapshotter, createInFlight, createBoundedInFlight, searchIndex, modelFailurePayload };
