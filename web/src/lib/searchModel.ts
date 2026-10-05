/**
 * Pure pieces of entity search shared by the /search page and the overlay. No React, no DOM,
 * so node's test runner can load it directly (test/searchModel.test.mjs).
 */
export type SearchTeam = { id: number; name: string; tag: string | null; tier: 1 | 2; logo: string | null };
export type SearchPlayer = { id: number; handle: string; real_name: string | null; team_id: number | null; team_name: string | null; photo: string | null };
export type SearchEvent = { id: number; name: string; tier: 1 | 2 };
export type SearchResults = { teams: SearchTeam[]; players: SearchPlayer[]; events: SearchEvent[] };

export const EMPTY_RESULTS: SearchResults = { teams: [], players: [], events: [] };
export const SEARCH_LIMIT = 20;
export const SEARCH_DEBOUNCE_MS = 200;

export const searchUrl = (query: string) => `/api/search?q=${encodeURIComponent(query.trim())}&limit=${SEARCH_LIMIT}`;

export function isSearchResults(data: unknown): data is SearchResults {
  const d = data as Partial<SearchResults> | null;
  return !!d && Array.isArray(d.teams) && Array.isArray(d.players) && Array.isArray(d.events);
}

/** Result rows you can open with the keyboard: teams, then players (events have no profile page). */
export interface LinkTarget { key: string; href: string }
export function linkTargets(r: SearchResults): LinkTarget[] {
  return [
    ...r.teams.map(t => ({ key: `t${t.id}`, href: `/team/${t.id}` })),
    ...r.players.map(p => ({ key: `p${p.id}`, href: `/player/${p.id}` })),
  ];
}

/** Arrow-key movement of the active row; wraps at both ends. Empty list -> -1. */
export function moveActive(current: number, delta: 1 | -1, count: number): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return delta === 1 ? 0 : count - 1;
  return (current + delta + count) % count;
}

/** "/" (not while typing) and Ctrl/Cmd+K open search. */
export function isSearchShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey?: boolean; defaultPrevented?: boolean },
  target: { isContentEditable?: boolean; tagName?: string } | null): "slash" | "mod-k" | null {
  if (e.defaultPrevented || e.altKey) return null;
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "k") return "mod-k";
  if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
    if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName ?? ""))) return null;
    return "slash";
  }
  return null;
}

/**
 * The overlay is open exactly while the current history entry carries this flag. Opening pushes one
 * entry (same URL + flag); Back pops it (closing the overlay without leaving the page); selecting a
 * result replaces it, so Back from the destination returns to the page that was under the overlay.
 */
export const OVERLAY_FLAG = "searchOverlay";
export function overlayOpen(state: unknown): boolean {
  return !!state && typeof state === "object" && (state as Record<string, unknown>)[OVERLAY_FLAG] === true;
}
export function withOverlay(state: unknown): Record<string, unknown> {
  return { ...(state && typeof state === "object" ? state as Record<string, unknown> : {}), [OVERLAY_FLAG]: true };
}
export function withoutOverlay(state: unknown): Record<string, unknown> | null {
  if (!state || typeof state !== "object") return null;
  const { [OVERLAY_FLAG]: _flag, ...rest } = state as Record<string, unknown>;
  return Object.keys(rest).length ? rest : null;
}
