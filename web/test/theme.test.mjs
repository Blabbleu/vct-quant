import test from "node:test";
import assert from "node:assert/strict";

async function loadTheme() {
  return import(`../src/lib/theme.ts?case=${Math.random()}`);
}

function browser({ initialTheme, light = false, saved, getItem, setItem } = {}) {
  const events = [];
  const listeners = new Set();
  const values = new Map();
  if (saved) values.set("vctq-theme", saved);
  const media = {
    matches: light,
    addEventListener: (_type, fn) => listeners.add(fn),
    removeEventListener: (_type, fn) => listeners.delete(fn),
    change(value) { this.matches = value; for (const fn of listeners) fn(); },
  };
  const storage = {
    getItem(key) { return getItem ? getItem(key, values) : values.get(key) ?? null; },
    setItem(key, value) { if (setItem) return setItem(key, value, values); values.set(key, value); },
  };
  const root = { dataset: {} };
  if (initialTheme) root.dataset.theme = initialTheme;
  globalThis.document = { documentElement: root };
  globalThis.window = {
    get localStorage() { return storage; },
    matchMedia: () => media,
    dispatchEvent: event => { events.push(event); return true; },
  };
  globalThis.CustomEvent = class CustomEvent { constructor(type, options) { this.type = type; this.detail = options.detail; } };
  return { root, media, events, values };
}

test("denied storage reads do not prevent import or theme resolution", async () => {
  const b = browser({ light: true });
  Object.defineProperty(window, "localStorage", { get() { throw new DOMException("denied", "SecurityError"); } });
  const theme = await loadTheme();
  assert.equal(theme.getTheme(), "light");
  assert.equal(b.root.dataset.theme, "light");
});

test("denied getItem falls back to system and explicit choice survives denied writes and OS changes", async () => {
  const b = browser({ light: false, getItem() { throw new DOMException("denied", "SecurityError"); }, setItem() { throw new DOMException("denied", "SecurityError"); } });
  const theme = await loadTheme();
  assert.equal(theme.getTheme(), "dark");
  assert.equal(theme.setTheme("light"), undefined);
  assert.equal(b.root.dataset.theme, "light");
  assert.equal(b.events.at(-1).type, "vctq-theme-change");
  assert.equal(b.events.at(-1).detail, "light");
  b.media.change(false);
  assert.equal(b.root.dataset.theme, "light");
  assert.equal(theme.toggleTheme(), "dark");
  assert.equal(b.root.dataset.theme, "dark");
  assert.equal(b.events.at(-1).detail, "dark");
  b.media.change(true);
  assert.equal(b.root.dataset.theme, "dark");
});

test("normal storage persists a selection and saved preference wins over OS changes", async () => {
  const b = browser({ light: true, saved: "dark" });
  const theme = await loadTheme();
  assert.equal(b.root.dataset.theme, "dark");
  theme.setTheme("light");
  assert.equal(b.values.get("vctq-theme"), "light");
  b.media.change(true);
  assert.equal(b.root.dataset.theme, "light");
});
