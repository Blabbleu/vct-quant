/**
 * In-process caching primitives for the python-backed API endpoints.
 *
 * Every slow endpoint shells out to `python -m vct_quant.<module>` (0.5-3.5 s
 * each, mostly pandas/duckdb import plus an Elo replay). The outputs only change
 * when the pipeline rewrites its input files, so we keep them in memory:
 *
 *   createStamper    stat() a list of input files -> one string that changes
 *                    whenever any of them is rewritten (mtime + size)
 *   createSwrCache   stale-while-revalidate cache keyed by id, invalidated by
 *                    that stamp plus a TTL ceiling, LRU-bounded, concurrent
 *                    identical requests coalesced
 *   createLimiter    caps simultaneous python processes
 *   createWarmer     recompute the expensive entries in the background at start
 *                    and once the input files have settled after a refresh
 *
 * Nothing here knows about http or python, so it is unit-tested with fakes.
 */
const fs = require("node:fs/promises");

function createLimiter(limit) {
  if (!Number.isSafeInteger(limit) || limit < 1) throw new RangeError("limit must be a positive integer");
  let active = 0;
  const queue = [];
  function drain() {
    while (active < limit && queue.length) {
      const { task, resolve, reject } = queue.shift();
      active += 1;
      Promise.resolve().then(task).then(resolve, reject).finally(() => {
        active -= 1;
        drain();
      });
    }
  }
  const run = task => new Promise((resolve, reject) => {
    queue.push({ task, resolve, reject });
    drain();
  });
  run.stats = () => ({ active, queued: queue.length });
  return run;
}

/**
 * One cheap fingerprint of a set of files. Missing files stamp as "-" so a file
 * appearing or disappearing also invalidates. `memoMs` collapses a burst of
 * requests into one round of stat() calls.
 */
function createStamper(paths, { memoMs = 0, now = Date.now, stat = fs.stat } = {}) {
  let memo = null;
  return async function readStamp() {
    if (memo && now() - memo.at < memoMs) return memo.value;
    const parts = await Promise.all(paths.map(file =>
      stat(file).then(s => `${s.mtimeMs}:${s.size}`, () => "-")));
    const value = parts.join("|");
    memo = { at: now(), value };
    return value;
  };
}

/**
 * Stale-while-revalidate cache.
 *
 * get(key) resolves with { value, state } where state is
 *   "hit"   fresh: same input stamp and younger than ttlMs
 *   "stale" served immediately; a background refresh was started (or is already
 *           running, or failed recently and is backing off)
 *   "miss"  nothing usable cached; waited for the computation
 * An entry older than maxStaleMs is never served: the caller waits instead.
 * A failed refresh keeps the stale entry (so a DuckDB writer holding the lock
 * during `vct update` does not turn into 500s) and retries after retryMs.
 * Failed misses throw and cache nothing. At most `max` keys are kept (LRU).
 */
function createSwrCache({
  compute, readStamp, ttlMs, maxStaleMs = ttlMs * 6, max = 200, retryMs = 5000,
  now = Date.now, onError = () => {},
}) {
  if (typeof compute !== "function" || typeof readStamp !== "function") throw new TypeError("compute and readStamp are required");
  if (!Number.isFinite(ttlMs) || ttlMs <= 0) throw new RangeError("ttlMs must be positive");
  if (!Number.isSafeInteger(max) || max < 1) throw new RangeError("max must be a positive integer");
  const entries = new Map();
  const pending = new Map();
  const failedAt = new Map();

  function remember(key, entry) {
    entries.delete(key);
    entries.set(key, entry);
    while (entries.size > max) entries.delete(entries.keys().next().value);
  }

  function refresh(key) {
    if (pending.has(key)) return pending.get(key);
    const promise = (async () => {
      // Stamp first: if the inputs change while we compute, the stored stamp is
      // already out of date and the next request recomputes.
      const stamp = await readStamp();
      const value = await compute(key);
      const entry = { value, stamp, at: now() };
      remember(key, entry);
      failedAt.delete(key);
      return entry;
    })();
    pending.set(key, promise);
    promise.then(() => {}, error => {
      failedAt.set(key, now());
      onError(key, error);
    }).finally(() => {
      if (pending.get(key) === promise) pending.delete(key);
    });
    return promise;
  }

  async function get(key, { waitForFresh = false } = {}) {
    const stamp = await readStamp();
    const entry = entries.get(key);
    if (entry) {
      const age = now() - entry.at;
      if (entry.stamp === stamp && age < ttlMs) {
        remember(key, entry);
        return { value: entry.value, state: "hit", stamp: entry.stamp, at: entry.at };
      }
      if (!waitForFresh && age < maxStaleMs) {
        remember(key, entry);
        const backingOff = failedAt.has(key) && now() - failedAt.get(key) < retryMs;
        if (!backingOff) refresh(key).catch(() => {});
        return { value: entry.value, state: "stale", stamp: entry.stamp, at: entry.at };
      }
    }
    const fresh = await refresh(key);
    return { value: fresh.value, state: "miss", stamp: fresh.stamp, at: fresh.at };
  }

  return {
    get,
    /** Recompute now (coalesced), whatever the current state. */
    refresh: key => refresh(key).then(entry => ({ value: entry.value, state: "miss", stamp: entry.stamp, at: entry.at })),
    peek: key => entries.get(key)?.value,
    has: key => entries.has(key),
    keys: () => [...entries.keys()],
    get size() { return entries.size; },
  };
}

/**
 * Background warm-up. `warm()` runs once at start() and again whenever `stamp()`
 * has changed and then stayed the same for `stableTicks` consecutive polls
 * (a refresh writes several files over a few seconds; recomputing mid-write
 * would hit the DuckDB lock and waste a process). It never throws and never
 * runs twice at once. Tests call tick() directly instead of waiting on timers.
 */
function createWarmer({ stamp, warm, intervalMs = 5000, stableTicks = 2, log = () => {} }) {
  let warmedStamp = null;
  let candidate = null;
  let seen = 0;
  let running = null;
  let timer = null;

  async function runWarm(reason, stampValue) {
    if (running) return running;
    running = (async () => {
      const started = Date.now();
      try {
        await warm();
        log(`warm-up (${reason}) done in ${((Date.now() - started) / 1000).toFixed(1)}s`);
      } catch (error) {
        log(`warm-up (${reason}) failed: ${error.message}`);
      } finally {
        warmedStamp = stampValue;
        running = null;
      }
    })();
    return running;
  }

  async function tick() {
    let value;
    try { value = await stamp(); } catch { return; }
    if (value === warmedStamp) { candidate = null; seen = 0; return; }
    if (value !== candidate) { candidate = value; seen = 1; } else seen += 1;
    if (seen >= stableTicks && !running) await runWarm("inputs changed", value);
  }

  return {
    tick,
    async start() {
      let value = null;
      try { value = await stamp(); } catch { /* warm anyway */ }
      const first = runWarm("start", value);
      timer = setInterval(() => { tick().catch(() => {}); }, intervalMs);
      timer.unref();
      return first;
    },
    stop() { if (timer) clearInterval(timer); timer = null; },
    get running() { return running !== null; },
  };
}

module.exports = { createLimiter, createStamper, createSwrCache, createWarmer };
