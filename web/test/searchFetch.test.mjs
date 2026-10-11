import test from "node:test";
import assert from "node:assert/strict";
import { isAbortError, loadSearch, searchUrl } from "../src/lib/searchModel.ts";
import { linkPath } from "../src/lib/linkPath.ts";

const results = { teams: [], players: [], events: [] };
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test("loadSearch fetches the trimmed query URL with its abort signal and returns valid results", async () => {
  const signal = new AbortController().signal;
  let requestedUrl;
  let requestedSignal;
  const loaded = await loadSearch("  Sentinels  ", signal, async (url, init) => {
    requestedUrl = url;
    requestedSignal = init.signal;
    return reply(200, results);
  });
  assert.equal(requestedUrl, searchUrl("Sentinels"));
  assert.equal(requestedSignal, signal);
  assert.deepEqual(loaded, results);
});

test("loadSearch reports the temporary unavailable message for 503", async () => {
  await assert.rejects(loadSearch("x", new AbortController().signal, async () => reply(503, {})), {
    message: "Search is temporarily unavailable. Try again shortly.",
  });
});

test("loadSearch includes the status for other HTTP errors", async () => {
  await assert.rejects(loadSearch("x", new AbortController().signal, async () => reply(500, {})), {
    message: "Search failed (500).",
  });
});

test("loadSearch rejects an invalid response body", async () => {
  await assert.rejects(loadSearch("x", new AbortController().signal, async () => reply(200, {})), {
    message: "Search returned an unexpected response.",
  });
});

test("isAbortError recognizes AbortError and rejects ordinary errors", () => {
  assert.equal(isAbortError(new DOMException("aborted", "AbortError")), true);
  assert.equal(isAbortError(new Error("ordinary failure")), false);
});

test("linkPath allows same-origin paths and rejects external, new-tab, and absent anchors", () => {
  assert.equal(linkPath({ pathname: "/team/1", origin: "https://desk.test", target: "" }, "https://desk.test"), "/team/1");
  assert.equal(linkPath({ pathname: "/", origin: "https://elsewhere.test", target: "" }, "https://desk.test"), null);
  assert.equal(linkPath({ pathname: "/", origin: "https://desk.test", target: "_blank" }, "https://desk.test"), null);
  assert.equal(linkPath(null, "https://desk.test"), null);
});
