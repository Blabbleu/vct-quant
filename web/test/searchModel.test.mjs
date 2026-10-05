import test from "node:test";
import assert from "node:assert/strict";
import {
  EMPTY_RESULTS, isSearchResults, isSearchShortcut, linkTargets, moveActive, overlayOpen, searchUrl, withOverlay, withoutOverlay,
} from "../src/lib/searchModel.ts";

const results = {
  teams: [{ id: 1, name: "G2", tag: "G2", tier: 1, logo: null }, { id: 2, name: "Karmine Corp", tag: "KC", tier: 1, logo: null }],
  players: [{ id: 9, handle: "leaf", real_name: null, team_id: null, team_name: null, photo: null }],
  events: [{ id: 5, name: "Champions", tier: 1 }],
};
const key = (k, extra = {}) => ({ key: k, ctrlKey: false, metaKey: false, altKey: false, ...extra });

test("search URL trims, encodes and carries the limit", () => {
  assert.equal(searchUrl("  Karmine Corp "), "/api/search?q=Karmine%20Corp&limit=20");
});

test("validates the response shape", () => {
  assert.equal(isSearchResults(results), true);
  assert.equal(isSearchResults({ teams: [] }), false);
  assert.equal(isSearchResults(null), false);
  assert.equal(isSearchResults(EMPTY_RESULTS), true);
});

test("keyboard targets are teams then players; events are not openable", () => {
  assert.deepEqual(linkTargets(results).map(t => t.href), ["/team/1", "/team/2", "/player/9"]);
  assert.deepEqual(linkTargets(EMPTY_RESULTS), []);
});

test("Up/Down move the active row and wrap", () => {
  assert.equal(moveActive(0, 1, 3), 1);
  assert.equal(moveActive(2, 1, 3), 0);
  assert.equal(moveActive(0, -1, 3), 2);
  assert.equal(moveActive(-1, 1, 3), 0);
  assert.equal(moveActive(-1, -1, 3), 2);
  assert.equal(moveActive(0, 1, 0), -1);
});

test("shortcuts: / outside fields, Ctrl/Cmd+K anywhere", () => {
  assert.equal(isSearchShortcut(key("/"), { tagName: "DIV" }), "slash");
  assert.equal(isSearchShortcut(key("/"), { tagName: "INPUT" }), null);
  assert.equal(isSearchShortcut(key("/"), { isContentEditable: true }), null);
  assert.equal(isSearchShortcut(key("/", { ctrlKey: true }), { tagName: "DIV" }), null);
  assert.equal(isSearchShortcut(key("k", { ctrlKey: true }), { tagName: "INPUT" }), "mod-k");
  assert.equal(isSearchShortcut(key("K", { metaKey: true }), null), "mod-k");
  assert.equal(isSearchShortcut(key("k"), null), null);
  assert.equal(isSearchShortcut(key("k", { ctrlKey: true, altKey: true }), null), null);
});

test("overlay open state lives in history state and is removable", () => {
  assert.equal(overlayOpen(null), false);
  assert.equal(overlayOpen({ focus: true }), false);
  const s = withOverlay({ focus: true });
  assert.equal(overlayOpen(s), true);
  assert.deepEqual(withoutOverlay(s), { focus: true });
  assert.equal(withoutOverlay(withOverlay(null)), null);
});
