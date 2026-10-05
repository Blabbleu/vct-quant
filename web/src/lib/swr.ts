/**
 * Tiny stale-while-revalidate store, shared by every page (module level, no deps).
 *
 *  - `get(key)` is what the UI renders: cached data shows at once on remount.
 *  - `load(key)` fetches only when the entry is missing or older than `freshMs`;
 *    concurrent loads of one key share a single request.
 *  - A background revalidation that fails keeps the last good data (no error
 *    panel over content). A forced load, or a load with nothing cached, reports
 *    the error like the original per-page fetch did.
 *  - The browser does the HTTP validation: the API answers `Cache-Control:
 *    no-cache` + ETag, so each revalidation is a conditional GET that costs a
 *    304 when nothing changed.
 *
 * No React in here so it runs under `node --test`.
 */

export type State<T> = { data: T | null; error: string | null; loading: boolean; refreshing: boolean };

type Entry = {
  state: State<unknown>;
  at: number;          // when `state.data` was last confirmed from the network
  ok: boolean;         // a successful response (including a 404 -> null) is cached
  inflight: Promise<void> | null;
  listeners: Set<() => void>;
};

export type Fetcher = (key: string) => Promise<unknown | null>;

export interface StoreOptions {
  fetcher: Fetcher;
  /** Entries younger than this are served without any request. */
  freshMs?: number;
  /** Max cached keys; entries with live subscribers are never evicted. */
  maxEntries?: number;
  now?: () => number;
}

const LOADING: State<never> = { data: null, error: null, loading: true, refreshing: false };

export function createStore({ fetcher, freshMs = 20_000, maxEntries = 150, now = Date.now }: StoreOptions) {
  const entries = new Map<string, Entry>();

  function entry(key: string): Entry {
    let e = entries.get(key);
    if (!e) {
      e = { state: LOADING, at: 0, ok: false, inflight: null, listeners: new Set() };
      entries.set(key, e);
      evict();
    } else {
      entries.delete(key); // re-insert: most recently used last
      entries.set(key, e);
    }
    return e;
  }

  function evict() {
    if (entries.size <= maxEntries) return;
    for (const [key, e] of entries) {
      if (entries.size <= maxEntries) break;
      if (e.listeners.size === 0 && !e.inflight) entries.delete(key);
    }
  }

  function set(e: Entry, state: State<unknown>) {
    e.state = state;
    for (const listener of [...e.listeners]) listener();
  }

  function isFresh(e: Entry, maxAge: number) {
    return e.ok && now() - e.at < maxAge;
  }

  function load(key: string, { force = false, maxAge = freshMs }: { force?: boolean; maxAge?: number } = {}): Promise<void> {
    const e = entry(key);
    if (e.inflight) {
      // A forced load that joins a request already under way still shows "loading".
      if (force && !e.state.loading) set(e, { ...e.state, loading: true });
      return e.inflight;
    }
    if (!force && isFresh(e, maxAge)) return Promise.resolve();
    const hadData = e.ok;
    set(e, force
      ? { ...e.state, loading: true, refreshing: hadData }
      : hadData ? { ...e.state, refreshing: true } : { ...LOADING });
    const request = Promise.resolve().then(() => fetcher(key)).then(
      data => {
        e.ok = true;
        e.at = now();
        set(e, { data: data as unknown, error: null, loading: false, refreshing: false });
      },
      (err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        if (hadData && !force) {
          // keep showing the last good payload; try again on the next visit
          e.ok = true;
          e.at = 0;
          set(e, { ...e.state, loading: false, refreshing: false });
        } else {
          e.ok = false;
          set(e, { data: null, error: message, loading: false, refreshing: false });
        }
      },
    ).finally(() => { e.inflight = null; });
    e.inflight = request;
    return request;
  }

  return {
    get<T>(key: string): State<T> {
      const e = entries.get(key);
      return (e ? e.state : LOADING) as State<T>;
    },
    subscribe(key: string, listener: () => void): () => void {
      const e = entry(key);
      e.listeners.add(listener);
      return () => { e.listeners.delete(listener); evict(); };
    },
    load,
    /** Warm a key without anyone watching it. Never throws. */
    prefetch(key: string): Promise<void> {
      return load(key).catch(() => {});
    },
    /** Drop a key so the next load starts from scratch. */
    invalidate(key: string) {
      const e = entries.get(key);
      if (!e) return;
      e.ok = false;
      e.at = 0;
    },
    /** Revalidate every key someone is watching (tab became visible again). */
    revalidateActive() {
      for (const [key, e] of entries) if (e.listeners.size > 0) void load(key);
    },
    has: (key: string) => entries.get(key)?.ok === true,
    size: () => entries.size,
  };
}
