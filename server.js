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

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 8000);
const HOST = process.env.HOST || "127.0.0.1";
const DB = path.join(ROOT, "data", "vct.duckdb");
const PYTHON = process.env.PYTHON ||
  path.join(ROOT, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

let cache = { stamp: null, payload: null };
let inFlight = null;

function computeSnapshot() {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ["-m", "vct_quant.dashboard"], { cwd: ROOT, maxBuffer: 64 << 20 },
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

async function snapshot() {
  // mtime is the cache key, so `vct update` invalidates without restarting.
  const stamp = await fs.stat(DB).then(s => String(s.mtimeMs), () => "no-db");
  if (cache.stamp === stamp && cache.payload) return cache.payload;
  // One python process even if ten requests land together.
  inFlight ??= computeSnapshot().finally(() => { inFlight = null; });
  const payload = await inFlight;
  cache = { stamp, payload };
  return payload;
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

const ROUTES = {
  "/api/snapshot": data => data,
  "/api/fixtures": data => data.fixtures,
  "/api/backtest": data => data.backtest,
  "/api/live": data => data.live,
  "/api/rankings": data => ({ season: data.season, rankings: data.rankings }),
  "/api/ledger": data => data.ledger,
  "/api/health": data => ({ ok: true, generated_at: data.generated_at, coverage: data.coverage }),
};

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, {
    "content-type": type,
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
  });
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
  const rel = path.normalize(decodeURIComponent(pathname)).replace(/^([/\\])+/, "");
  const file = path.join(DIST, rel);
  const ext = path.extname(rel);
  if (rel && ext && ext !== ".html" && file.startsWith(DIST + path.sep)) {
    try {
      const body = await fs.readFile(file);
      res.writeHead(200, {
        "content-type": TYPES[ext] || "application/octet-stream",
        "content-length": body.length,
        "cache-control": rel.startsWith("assets/") ? "public, max-age=31536000, immutable" : "no-cache",
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
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (req.method !== "GET" && req.method !== "HEAD") {
    return send(res, 405, JSON.stringify({ error: "read-only API: GET only" }));
  }
  const route = ROUTES[url.pathname];
  if (route) {
    try {
      return send(res, 200, JSON.stringify(route(await snapshot())));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({
        error: "the model layer failed",
        detail: err.message,
        hint: "run `vct init-db` and `vct update` first, or set PYTHON to your interpreter",
      }));
    }
  }
  const match = /^\/api\/match\/([1-9][0-9]*)$/.exec(url.pathname);
  if (match && Number.isSafeInteger(Number(match[1]))) {
    try {
      const result = await computeMatch(match[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "match not found in prediction log" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the match layer failed" }));
    }
  }
  const team = /^\/api\/team\/([1-9][0-9]*)$/.exec(url.pathname);
  if (team && Number.isSafeInteger(Number(team[1]))) {
    try {
      const result = await computeTeam(team[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "team not found in Tier-1 history or cached fixtures" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the team layer failed" }));
    }
  }
  const player = /^\/api\/player\/([1-9][0-9]*)$/.exec(url.pathname);
  if (player && Number.isSafeInteger(Number(player[1]))) {
    try {
      const result = await computePlayer(player[1]);
      return result === null
        ? send(res, 404, JSON.stringify({ error: "player ID not found" }))
        : send(res, 200, JSON.stringify(result));
    } catch (err) {
      console.error(`[500] ${url.pathname}: ${err.message}`);
      return send(res, 500, JSON.stringify({ error: "the player layer failed" }));
    }
  }
  if (url.pathname.startsWith("/api/")) {
    return send(res, 404, JSON.stringify({ error: "not found", routes: Object.keys(ROUTES) }));
  }
  const logo = /^\/logos\/([1-9][0-9]{0,9})\.(png|jpg|webp|svg)$/.exec(url.pathname);
  if (logo) {
    try {
      const body = await fs.readFile(path.join(ROOT, "data", "processed", "logos", `${logo[1]}.${logo[2]}`));
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

module.exports = { server, snapshot, ROUTES };
