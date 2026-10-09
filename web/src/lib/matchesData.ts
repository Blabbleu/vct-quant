/**
 * Pure helpers behind the Matches page, its event strip and the right rail.
 * Everything here derives from the existing /api payloads; nothing is invented.
 * Type-only imports keep this file runnable under `node --test` (see test/matchesData.test.mjs).
 */
import type { ChampionsPlayoffMatch, ChampionsPlayoffSlot, ChampionsPlayoffs, Fixture, ResultRow } from "./types";

/** The next named, unplayed playoff series, with the opening slate as a pre-draw fallback. */
export function nextPlayoffSeries(playoffs: ChampionsPlayoffs | undefined, limit = 4): (ChampionsPlayoffMatch | ChampionsPlayoffSlot)[] {
  if (!playoffs) return [];
  const unverified = new Set(playoffs.unverified_match_ids ?? []);
  const named = [...playoffs.opening, ...playoffs.schedule]
    .filter(s => s.sides?.length === 2 && s.sides.every(side => side.name.trim().length > 0)
      && s.result == null && !unverified.has(s.match_id))
    .sort((a, b) => (a.start ?? "9").localeCompare(b.start ?? "9") || a.match_id - b.match_id);
  if (named.length > 0) return named.slice(0, limit);
  return [...playoffs.opening]
    .sort((a, b) => (a.start ?? "9").localeCompare(b.start ?? "9") || a.match_id - b.match_id)
    .slice(0, limit);
}

/* ---------------------------------------------------------------- stage names */

/** "Playoffs: Upper Quarterfinals" -> { phase: "Playoffs", stage: "Upper Quarterfinals" }. */
export function stageParts(series: string | null | undefined): { phase: string | null; stage: string } {
  const s = (series ?? "").trim();
  const i = s.indexOf(":");
  if (i < 0) return { phase: null, stage: s };
  return { phase: s.slice(0, i).trim() || null, stage: s.slice(i + 1).trim() };
}

const ABBREV: [RegExp, string][] = [
  [/\bQuarterfinals?\b/i, "QF"],
  [/\bSemifinals?\b/i, "SF"],
  [/\bRound (\d+)\b/i, "R$1"],
];

/** Short stage label that fits a card header: "Upper Quarterfinals" -> "Upper QF", "Lower Round 1" -> "Lower R1". */
export function stageShort(series: string | null | undefined): string {
  let { stage } = stageParts(series);
  for (const [re, to] of ABBREV) stage = stage.replace(re, to);
  return stage;
}

/** "Upper QF · Bo3" (or just the stage when the best-of is unknown). */
export function stageLabel(f: Pick<Fixture, "series" | "best_of">): string {
  const s = stageShort(f.series);
  return f.best_of ? `${s}${s ? " \u00B7 " : ""}Bo${f.best_of}` : s;
}

/* ------------------------------------------------------------------ countdown */

/** "2D 14H 03M" for 1+ days, "14H 03M 22S" under a day, "03M 22S" under an hour, "LIVE" once started. */
export function formatCountdown(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "LIVE";
  const total = Math.floor(ms / 1000);
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const mi = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const p2 = (n: number) => String(n).padStart(2, "0");
  if (d > 0) return `${d}D ${p2(h)}H ${p2(mi)}M`;
  if (h > 0) return `${p2(h)}H ${p2(mi)}M ${p2(s)}S`;
  return `${p2(mi)}M ${p2(s)}S`;
}

/* ------------------------------------------------------------ grouping/context */

export interface DayGroup<T> { key: string; label: string; items: T[] }

/** Group items (already sorted) by local calendar day; `fmt` supplies the heading. */
export function groupByDay<T extends { start: string }>(items: T[], fmt: (d: Date) => string): DayGroup<T>[] {
  const out: DayGroup<T>[] = [];
  for (const it of items) {
    const label = fmt(new Date(it.start));
    const last = out[out.length - 1];
    if (last && last.label === label) last.items.push(it);
    else out.push({ key: label, label, items: [it] });
  }
  return out;
}

export interface EventContext {
  event: string;
  phase: string | null;
  /** Distinct stages in kick-off order, e.g. ["Upper Quarterfinals"]. */
  stages: string[];
  matches: number;
  days: number;
  bestOf: number[];
  next: Fixture;
}

/** The event/stage the strip talks about: that of the soonest fixture, counted over `fixtures`. */
export function eventContext(fixtures: Fixture[], dayKey: (d: Date) => string): EventContext | null {
  const sorted = [...fixtures].sort((a, b) => a.start.localeCompare(b.start));
  const next = sorted[0];
  if (!next) return null;
  const same = sorted.filter(f => f.event === next.event);
  const stages: string[] = [];
  for (const f of same) {
    const st = stageParts(f.series).stage;
    if (st && !stages.includes(st)) stages.push(st);
  }
  const bestOf = [...new Set(same.map(f => f.best_of).filter((b): b is number => b != null))].sort();
  return {
    event: next.event,
    phase: stageParts(next.series).phase,
    stages,
    matches: same.length,
    days: new Set(same.map(f => dayKey(new Date(f.start)))).size,
    bestOf,
    next,
  };
}

/* -------------------------------------------------------------------- results */

/** Did the model's pick (the side it gave >= 50%) win? null for an unverified/unscored row. */
export function pickHit(r: Pick<ResultRow, "p_a" | "result">): boolean | null {
  const w = r.result.status === "verified" ? r.result.winner : null;
  if (w == null) return null;
  return (w === "a") === (r.p_a >= 0.5);
}

/** The model's pick as a side and its probability. */
export function pickSide(r: Pick<ResultRow, "p_a">): { side: "a" | "b"; p: number } {
  return r.p_a >= 0.5 ? { side: "a", p: r.p_a } : { side: "b", p: 1 - r.p_a };
}

/** Verified rows, newest kick-off first. */
export function verifiedNewestFirst(rows: ResultRow[]): ResultRow[] {
  return rows
    .filter(r => r.result.status === "verified" && r.result.winner != null)
    .sort((a, b) => b.scheduled_at.localeCompare(a.scheduled_at) || b.match_id - a.match_id);
}

/** Newest verified results: everything inside `hours` of the latest one, but never fewer than `min` or more than `max`. */
export function justFinished(rows: ResultRow[], { hours = 48, min = 4, max = 6 } = {}): ResultRow[] {
  const v = verifiedNewestFirst(rows);
  if (v.length === 0) return [];
  const newest = new Date(v[0].scheduled_at).getTime();
  const recent = v.filter(r => newest - new Date(r.scheduled_at).getTime() <= hours * 3_600_000);
  let n = Math.min(max, Math.max(min, recent.length));
  if (n % 2 === 1 && n < max && n < v.length) n += 1; // even count: the two-column grid never ends on a hole
  return v.slice(0, n);
}

/** The model's worst verified calls by log loss (misses first). */
export function biggestMisses(rows: ResultRow[], n: number): ResultRow[] {
  return verifiedNewestFirst(rows)
    .filter(r => pickHit(r) === false && r.log_loss != null)
    .sort((a, b) => (b.log_loss as number) - (a.log_loss as number))
    .slice(0, n);
}

/* ------------------------------------------------------------ event timeline */

export interface TimelineStage { stage: string; short: string; start: string; end: string; matches: number; bestOf: number | null; past: boolean; current: boolean }

/** The event's stages in order from the Champions playoff feed (opening matches + published schedule). */
export function stageTimeline(playoffs: ChampionsPlayoffs | undefined, currentSeries: string | null, now = Date.now()): TimelineStage[] {
  if (!playoffs) return [];
  const slots = [...playoffs.opening, ...playoffs.schedule]
    .map(s => ({ ...s, timelineDate: s.start ?? s.played_on ?? null }))
    .filter(s => s.timelineDate != null);
  slots.sort((a, b) => (a.timelineDate as string).localeCompare(b.timelineDate as string));
  const out: TimelineStage[] = [];
  const cur = currentSeries ? stageParts(currentSeries).stage : null;
  for (const s of slots) {
    const found = out.find(o => o.stage === s.stage);
    if (found) {
      found.end = s.timelineDate as string;
      found.matches += 1;
    } else {
      out.push({
        stage: s.stage, short: stageShort(s.stage), start: s.timelineDate as string, end: s.timelineDate as string,
        matches: 1, bestOf: s.best_of, past: false, current: false,
      });
    }
  }
  for (const o of out) {
    o.past = new Date(o.end).getTime() < now;
    o.current = cur != null && o.stage === cur;
  }
  return out;
}
