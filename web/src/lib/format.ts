export const pct = (p: number | null | undefined, digits = 1) =>
  p == null || !Number.isFinite(p) ? "–" : `${(p * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 4) =>
  v == null || !Number.isFinite(v) ? "–" : v.toFixed(digits);

export const int = (v: number) => v.toLocaleString("en-US");

const dtf = new Intl.DateTimeFormat(undefined, {
  weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});
export const when = (iso: string) => dtf.format(new Date(iso));

export function relative(iso: string, now = Date.now()): string {
  const mins = Math.round((new Date(iso).getTime() - now) / 60000);
  if (mins === 0) return "now";
  const abs = Math.abs(mins);
  const text = abs < 60 ? `${abs}m` : abs < 48 * 60 ? `${Math.round(abs / 60)}h` : `${Math.round(abs / 1440)}d`;
  return mins >= 0 ? `in ${text}` : `${text} ago`;
}

/** The model's own formula: a 400-point Elo edge is 10:1 series odds. */
export const eloWinProbability = (a: number, b: number) => 1 / (1 + Math.pow(10, (b - a) / 400));

/** A market quote worth comparing against: priced, tight and traded. */
export const liquid = (spread: number | null, volume: number | null) =>
  spread != null && spread <= 0.1 && (volume ?? 0) >= 1000;

export const logLoss = (p: number, won: boolean) => -Math.log(Math.min(Math.max(won ? p : 1 - p, 1e-9), 1));

function withUtcZone(iso: string): string {
  return /[Zz]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
}

const bracketDayFmt = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" });
const bracketTimeFmt = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false });

function parseUtc(iso: string | null): Date | null {
  if (!iso) return null;
  const date = new Date(withUtcZone(iso));
  return Number.isFinite(date.getTime()) ? date : null;
}

function utcDaySpan(start: Date, end: Date): string {
  const a = bracketDayFmt.format(start), b = bracketDayFmt.format(end);
  if (start.getUTCFullYear() === end.getUTCFullYear() && start.getUTCMonth() === end.getUTCMonth() && start.getUTCDate() === end.getUTCDate()) return a;
  const sameMonth = start.getUTCFullYear() === end.getUTCFullYear() && start.getUTCMonth() === end.getUTCMonth();
  return `${a}–${sameMonth ? b.replace(/^\w+ /, "") : b}`;
}

/** UTC date span for a stage timeline, with a useful fallback for a missing end. */
export function stageSpan(start: string | null, end: string | null): string {
  const a = parseUtc(start);
  if (!a) return "";
  const b = parseUtc(end);
  return b ? utcDaySpan(a, b) : bracketDayFmt.format(a);
}

/** Compact bracket kickoff, matching its UTC legend. */
export function bracketKickoff(iso: string | null): string {
  const date = parseUtc(iso);
  return date ? `${bracketDayFmt.format(date)} · ${bracketTimeFmt.format(date)}` : "Time TBD";
}

/** Date-only label for a completed bracket match, formatted in UTC. */
export function playedDate(iso: string | null): string {
  const date = parseUtc(iso);
  return date ? `Played ${bracketDayFmt.format(date)}` : "Time TBD";
}

/** Round date range and best-of labels for bracket headings. */
export function bracketRoundSub(starts: (string | null)[], bestOf: (number | null)[]): string {
  const days = starts.map(parseUtc).filter((date): date is Date => date != null).sort((a, b) => a.getTime() - b.getTime());
  const bo = [...new Set(bestOf.filter((b): b is number => b != null))];
  const parts: string[] = [];
  if (days.length) {
    parts.push(utcDaySpan(days[0], days[days.length - 1]));
  }
  if (bo.length) parts.push(bo.map(b => `Bo${b}`).join("/"));
  return parts.join(" · ");
}

/** Kick-off for prose, e.g. "Oct 8, 2026, 9:00 AM UTC". */
export function utc(iso: string | null): string {
  if (!iso) return "an unknown time";
  const withZone = withUtcZone(iso);
  if (!Number.isFinite(new Date(withZone).getTime())) return "an unknown time";
  return `${new Date(withZone).toLocaleString(undefined, { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC`;
}

/** Compact kick-off, e.g. "Oct 08, 09:00 UTC". */
export function utcShort(iso: string | null): string {
  if (!iso) return "Time TBD";
  const withZone = withUtcZone(iso);
  if (!Number.isFinite(new Date(withZone).getTime())) return "Time TBD";
  return `${new Date(withZone).toLocaleString("en-US", { timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })} UTC`;
}
