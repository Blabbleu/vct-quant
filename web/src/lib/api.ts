import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import type { Movement, Snapshot, TeamProfile, PlayerProfile, ChampionsStatus, PaperLedger, ResultsList, OpsStatus } from "./types";
import { createStore, type State } from "./swr";
import { URLS } from "./urls";

export type { State };
export { URLS };

async function getJson(url: string): Promise<unknown | null> {
  const resp = await fetch(url);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`${url} answered ${resp.status}`);
  return resp.json();
}

/**
 * One cache for the whole app, keyed by URL. Pages render cached data at once on
 * every revisit and revalidate in the background; the server answers
 * `Cache-Control: no-cache` + ETag, so a revalidation is a 304 when nothing changed.
 */
export const store = createStore({ fetcher: getJson, freshMs: 20_000 });

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") store.revalidateActive();
  });
}

/** Warm the cache for a URL (no-op when fresh, shared with any request in flight). */
export function prefetch(url: string) { return store.prefetch(url); }

/** Read through the cache outside React (cached copy if fresh, else one shared request). Resolves null on 404 or error. */
export async function loadCached<T>(url: string): Promise<T | null> {
  await store.load(url).catch(() => {});
  return store.get<T>(url).data;
}

/** The next snapshot read refetches (kept for callers that want a hard refresh). */
export function refreshSnapshot() { store.invalidate(URLS.snapshot); }

const IDLE: State<never> = { data: null, error: null, loading: false, refreshing: false };

/**
 * @param url    null disables the hook (nothing fetched, `loading` false).
 * @param nonce  bump to force a refetch even when the cached copy is fresh.
 * @param maxAge how old a cached copy may be before mounting revalidates it.
 */
export function useCached<T>(url: string | null, nonce = 0, maxAge?: number): State<T> {
  const subscribe = useCallback((listener: () => void) => (url ? store.subscribe(url, listener) : () => {}), [url]);
  const read = useCallback(() => (url ? store.get<T>(url) : (IDLE as State<T>)), [url]);
  const state = useSyncExternalStore(subscribe, read, read);
  useEffect(() => {
    if (url) void store.load(url, { force: nonce > 0, maxAge });
  }, [url, nonce, maxAge]);
  return state;
}

export function useSnapshot(nonce = 0): State<Snapshot> { return useCached<Snapshot>(URLS.snapshot, nonce); }
export function useMovement(id: number): State<Movement> { return useCached<Movement>(URLS.match(id)); }
export function useTeamProfile(id: number): State<TeamProfile> { return useCached<TeamProfile>(URLS.team(id)); }
export function usePlayerProfile(id: number): State<PlayerProfile> { return useCached<PlayerProfile>(URLS.player(id)); }
export function usePaperLedger(): State<PaperLedger> { return useCached<PaperLedger>(URLS.paperLedger); }
export function useResults(): State<ResultsList> { return useCached<ResultsList>(URLS.results); }
export function useChampionsStatus(): State<ChampionsStatus> { return useCached<ChampionsStatus>(URLS.champions); }
/**
 * Ops is about freshness: the last copy shows at once, but every visit revalidates it, and
 * `loading` stays true during that check (the Status page shows "Checking..." and stamps the time).
 */
export function useOps(nonce = 0): State<OpsStatus> {
  const state = useCached<OpsStatus>(URLS.ops, nonce, 0);
  return useMemo(() => (state.refreshing && !state.loading ? { ...state, loading: true } : state), [state]);
}
