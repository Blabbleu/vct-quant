import type { ComponentType } from "react";
import { prefetch } from "./api";
import { IDLE_PREFETCH, planForPath } from "./urls";

/**
 * Warm the client cache (and the lazy Champions chunk) before the user needs it:
 *  - once at start-up when the browser is idle,
 *  - on pointer hover (mouse only, 80 ms intent delay), keyboard focus and touchstart
 *    of any in-app link, via one delegated listener, so every Link (nav, team, player,
 *    match) gets it without touching the components.
 * Respects Save-Data and never throws; all requests share the cache's in-flight dedupe.
 */
let championsPage: ComponentType | null = null;
/** Resolves the lazy Champions chunk once; later route renders then skip Suspense (and its 300 ms fallback throttle). */
export function loadChampions() {
  return import("../pages/Champions").then(mod => { championsPage = mod.default; return mod; });
}
/** The Champions page component if its chunk has already arrived, else null. */
export const loadedChampions = () => championsPage;

const chunks: Record<string, () => Promise<unknown>> = { champions: loadChampions };

function saveData(): boolean {
  const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return conn?.saveData === true;
}

function warmPath(pathname: string) {
  const plan = planForPath(pathname);
  if (!plan) return;
  for (const url of plan.urls) void prefetch(url);
  if (plan.chunk) void chunks[plan.chunk]().catch(() => {});
}

function linkPath(target: EventTarget | null): string | null {
  const anchor = target instanceof Element ? target.closest("a[href]") : null;
  if (!(anchor instanceof HTMLAnchorElement) || anchor.target === "_blank") return null;
  if (anchor.origin !== location.origin) return null;
  return anchor.pathname;
}

export function installPrefetch() {
  if (typeof window === "undefined") return;
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
  const whenIdle = (cb: () => void) => (idle ? idle(cb, { timeout: 2000 }) : window.setTimeout(cb, 300));
  if (!saveData()) {
    whenIdle(() => { for (const url of IDLE_PREFETCH) void prefetch(url); void chunks.champions().catch(() => {}); });
  }

  let timer = 0;
  document.addEventListener("pointerover", e => {
    if (e.pointerType !== "mouse" || saveData()) return;
    const path = linkPath(e.target);
    window.clearTimeout(timer);
    if (path) timer = window.setTimeout(() => warmPath(path), 80);
  }, { passive: true });
  document.addEventListener("pointerout", () => window.clearTimeout(timer), { passive: true });
  document.addEventListener("focusin", e => {
    const path = linkPath(e.target);
    if (path && !saveData()) warmPath(path);
  });
  document.addEventListener("touchstart", e => {
    const path = linkPath(e.target);
    if (path && !saveData()) warmPath(path);
  }, { passive: true });
}
