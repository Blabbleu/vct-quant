/** API endpoints and the data each route needs, as plain strings (no React, testable under node). */
export const URLS = {
  snapshot: "/api/snapshot",
  results: "/api/results",
  champions: "/api/champions/2766",
  paperLedger: "/api/paper-ledger",
  ops: "/api/ops",
  match: (id: number | string) => `/api/match/${id}`,
  team: (id: number | string) => `/api/team/${id}`,
  player: (id: number | string) => `/api/player/${id}`,
};

export type RoutePlan = { urls: string[]; chunk?: "champions" };

/**
 * What a page fetches when it mounts, by pathname. Used to warm the client cache
 * before the click lands (hover, focus, touchstart) and once at start-up.
 * Keep in step with the hooks each page calls.
 */
export function planForPath(pathname: string): RoutePlan | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (path === "/") return { urls: [URLS.snapshot, URLS.results] };
  if (path === "/matches") return { urls: [URLS.snapshot, URLS.results, URLS.champions] };
  if (path === "/results") return { urls: [URLS.results, URLS.snapshot] };
  if (path === "/rankings") return { urls: [URLS.snapshot, URLS.results] };
  if (path === "/champions/2766") return { urls: [URLS.champions], chunk: "champions" };
  if (path === "/edge") return { urls: [URLS.snapshot, URLS.paperLedger] };
  if (path === "/track-record") return { urls: [URLS.snapshot] };
  if (path === "/status") return { urls: [URLS.ops] };
  const match = /^\/(match|team|player)\/([1-9][0-9]{0,15})$/.exec(path);
  if (match) {
    const [, kind, id] = match;
    if (kind === "match") return { urls: [URLS.snapshot, URLS.match(id)] };
    if (kind === "team") return { urls: [URLS.team(id)] };
    return { urls: [URLS.player(id)] };
  }
  return null;
}

/** Fetched once the app is idle after first paint, whatever the landing page. */
export const IDLE_PREFETCH = [URLS.snapshot, URLS.results, URLS.champions];
