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

function computeMatch(matchId) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.match_center", matchId],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from match center: ${parseError.message}`));
        }
      });
  });
}

function computeTeam(teamId) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.team_profile", teamId],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from team profile: ${parseError.message}`));
        }
      });
  });
}

function computePlayer(playerId) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.player_profile", playerId],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from player profile: ${parseError.message}`));
        }
      });
  });
}

const computeMatchInFlight = createBoundedInFlight(computeMatch, 2, 16);
const computeTeamInFlight = createBoundedInFlight(computeTeam, 2, 16);
const computePlayerInFlight = createBoundedInFlight(computePlayer, 2, 16);

function computeChampions() {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.champions_status"],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from Champions status: ${parseError.message}`));
        }
      });
  });
}

function computeResults() {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.results_list"],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from results list: ${parseError.message}`));
        }
      });
  });
}

function computePaperLedger() {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.paper_ledger"],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from paper ledger: ${parseError.message}`));
        }
      });
  });
}

function computeOps() {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.ops_status"],
      { cwd: ROOT, maxBuffer: 8 << 20, timeout: 30000 }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr.trim() || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`bad JSON from ops status: ${parseError.message}`));
        }
      });
  });
}

// Share simultaneous reads without caching completed values. This avoids
// duplicate Python processes while preserving freshness on later requests.
const computeChampionsInFlight = createInFlight(computeChampions);
const computePaperLedgerInFlight = createInFlight(computePaperLedger);
const computeResultsInFlight = createInFlight(computeResults);
const computeOpsInFlight = createInFlight(computeOps);

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
      return send(res, 200, JSON.stringify(route(await snapshot())));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify(modelFailurePayload()));
    }
  }
  const match = /^\/api\/match\/([1-9][0-9]*)$/.exec(url.pathname);
  if (match && Number.isSafeInteger(Number(match[1]))) {
    try {
      const result = await computeMatchInFlight(match[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "match not found in prediction log" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      if (err.code === "OVERLOADED") {
        res.setHeader("retry-after", "1");
        return send(res, 503, JSON.stringify({ error: "match lookups are busy; retry shortly" }));
      }
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the match layer failed" }));
    }
  }
  const team = /^\/api\/team\/([1-9][0-9]*)$/.exec(url.pathname);
  if (team && Number.isSafeInteger(Number(team[1]))) {
    try {
      const result = await computeTeamInFlight(team[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "team not found in Tier-1 history or cached fixtures" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      if (err.code === "OVERLOADED") {
        res.setHeader("retry-after", "1");
        return send(res, 503, JSON.stringify({ error: "team lookups are busy; retry shortly" }));
      }
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the team layer failed" }));
    }
  }
  const player = /^\/api\/player\/([1-9][0-9]*)$/.exec(url.pathname);
  if (player && Number.isSafeInteger(Number(player[1]))) {
    try {
      const result = await computePlayerInFlight(player[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "player ID not found" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      if (err.code === "OVERLOADED") {
        res.setHeader("retry-after", "1");
        return send(res, 503, JSON.stringify({ error: "player lookups are busy; retry shortly" }));
      }
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the player layer failed" }));
    }
  }
  if (url.pathname === "/api/champions/2766") {
    try {
      return send(res, 200, JSON.stringify(await computeChampionsInFlight("champions")));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the Champions layer failed" }));
    }
  }
  if (url.pathname === "/api/paper-ledger") {
    try {
      return send(res, 200, JSON.stringify(await computePaperLedgerInFlight("paper-ledger")));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the paper ledger failed" }));
    }
  }
  if (url.pathname === "/api/results") {
    try {
      return send(res, 200, JSON.stringify(await computeResultsInFlight("results")));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the results list failed" }));
    }
  }
  if (url.pathname === "/api/ops") {
    // Uncached on purpose: freshness is the point, and it reads only local files.
    try {
      return send(res, 200, JSON.stringify(await computeOpsInFlight("ops")));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the ops status failed" }));
    }
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
  });
}

module.exports = { server, snapshot, ROUTES, computeSnapshot, createSnapshotter, createInFlight, createBoundedInFlight, searchIndex, modelFailurePayload };
