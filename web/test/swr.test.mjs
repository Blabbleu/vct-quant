import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../src/lib/swr.ts";
import { IDLE_PREFETCH, URLS, planForPath } from "../src/lib/urls.ts";

function harness(options = {}) {
  let time = 1000;
  const calls = [];
  const gates = new Map();
  const fetcher = key => {
    calls.push(key);
    if (options.fail?.has(key)) return Promise.reject(new Error(`${key} answered 500`));
    if (options.hold) return new Promise((resolve, reject) => gates.set(key, { resolve, reject }));
    return Promise.resolve(options.reply ? options.reply(key, calls.length) : { key, n: calls.length });
  };
  const store = createStore({ fetcher, freshMs: 1000, now: () => time, ...options.store });
  return { store, calls, gates, advance: ms => { time += ms; }, fail: options.fail };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test("first load reports loading, then data; a fresh remount does not refetch", async () => {
  const { store, calls } = harness();
  assert.deepEqual(store.get("/a"), { data: null, error: null, loading: true, refreshing: false });
  await store.load("/a");
  assert.equal(store.get("/a").loading, false);
  assert.deepEqual(store.get("/a").data, { key: "/a", n: 1 });
  await store.load("/a");
  assert.equal(calls.length, 1, "inside freshMs the cached copy is served with no request");
});

test("stale entries show cached data at once while revalidating (no loading flag)", async () => {
  const { store, calls, advance } = harness();
  await store.load("/a");
  advance(5000);
  const seen = [];
  store.subscribe("/a", () => seen.push({ ...store.get("/a") }));
  const pending = store.load("/a");
  const during = store.get("/a");
  assert.equal(during.loading, false, "revisit must not show a skeleton");
  assert.equal(during.refreshing, true);
  assert.equal(during.data.n, 1, "old data stays visible during revalidation");
  await pending;
  assert.equal(calls.length, 2);
  assert.equal(store.get("/a").data.n, 2);
  assert.equal(store.get("/a").refreshing, false);
  assert.ok(seen.length >= 2, "subscribers are notified of both transitions");
});

test("concurrent identical loads share one request", async () => {
  const { store, calls, gates } = harness({ hold: true });
  const all = Promise.all([store.load("/a"), store.load("/a"), store.load("/a"), store.prefetch("/a")]);
  await settle();
  assert.equal(calls.length, 1);
  gates.get("/a").resolve({ ok: true });
  await all;
  assert.deepEqual(store.get("/a").data, { ok: true });
});

test("a failed first load surfaces the error; the next load retries", async () => {
  const fail = new Set(["/a"]);
  const { store, calls } = harness({ fail });
  await store.load("/a");
  assert.equal(store.get("/a").error, "/a answered 500");
  assert.equal(store.get("/a").loading, false);
  assert.equal(store.get("/a").data, null);
  fail.delete("/a");
  await store.load("/a");
  assert.equal(calls.length, 2, "errors are never treated as fresh");
  assert.equal(store.get("/a").error, null);
});

test("a failed background revalidation keeps the last good data", async () => {
  const fail = new Set();
  const { store, advance } = harness({ fail });
  await store.load("/a");
  advance(5000);
  fail.add("/a");
  await store.load("/a");
  const state = store.get("/a");
  assert.equal(state.error, null, "no error panel over content that is already on screen");
  assert.equal(state.data.n, 1);
  assert.equal(state.refreshing, false);
  fail.delete("/a");
  await store.load("/a");
  assert.equal(store.get("/a").data.n, 3, "a failed revalidation is retried on the next visit");
});

test("forced load (Recheck) reports loading and surfaces errors but keeps data", async () => {
  const fail = new Set();
  const { store } = harness({ fail });
  await store.load("/ops");
  fail.add("/ops");
  const pending = store.load("/ops", { force: true });
  assert.equal(store.get("/ops").loading, true);
  assert.equal(store.get("/ops").data.n, 1);
  await pending;
  assert.equal(store.get("/ops").error, "/ops answered 500");
});

test("maxAge 0 revalidates on every load (ops), maxAge default respects freshMs", async () => {
  const { store, calls } = harness();
  await store.load("/ops", { maxAge: 0 });
  await store.load("/ops", { maxAge: 0 });
  assert.equal(calls.length, 2);
});

test("null (404) is a cached answer, not an error", async () => {
  const { store, calls } = harness({ reply: () => null });
  await store.load("/team/9");
  assert.deepEqual(store.get("/team/9"), { data: null, error: null, loading: false, refreshing: false });
  await store.load("/team/9");
  assert.equal(calls.length, 1);
});

test("bounded: old unwatched entries are evicted, watched ones are kept", async () => {
  const { store } = harness({ store: { maxEntries: 3 } });
  const stop = store.subscribe("/watched", () => {});
  for (const key of ["/a", "/b", "/c", "/d", "/e"]) await store.load(key);
  assert.ok(store.size() <= 4, `size ${store.size()}`);
  assert.equal(store.has("/e"), true, "newest entries survive");
  assert.equal(store.has("/a"), false, "oldest unwatched entry is evicted");
  stop();
});

test("invalidate forces the next load to refetch; prefetch never throws", async () => {
  const fail = new Set(["/x"]);
  const { store, calls } = harness({ fail });
  await store.load("/a");
  store.invalidate("/a");
  await store.load("/a");
  assert.equal(calls.length, 2);
  await store.prefetch("/x");
  assert.equal(store.get("/x").error, "/x answered 500");
});

test("route plans cover what each page fetches", () => {
  assert.deepEqual(planForPath("/").urls, [URLS.snapshot, URLS.results]);
  assert.deepEqual(planForPath("/matches").urls, [URLS.snapshot, URLS.results, URLS.champions]);
  assert.deepEqual(planForPath("/champions/2766"), { urls: [URLS.champions], chunk: "champions" });
  assert.deepEqual(planForPath("/team/11058/").urls, ["/api/team/11058"]);
  assert.deepEqual(planForPath("/player/9801").urls, ["/api/player/9801"]);
  assert.deepEqual(planForPath("/match/754732").urls, [URLS.snapshot, "/api/match/754732"]);
  assert.equal(planForPath("/about"), null);
  assert.equal(planForPath("/team/abc"), null);
  assert.equal(planForPath("/team/0"), null);
  assert.deepEqual(IDLE_PREFETCH, [URLS.snapshot, URLS.results, URLS.champions]);
});
